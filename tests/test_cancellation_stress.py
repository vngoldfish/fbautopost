"""
tests/test_cancellation_stress.py
Empirical Challenge and Adversarial Stress-Test Suite for Backend Task Cancellation
Role: Challenger 1 (challenger_m4_1)

Validates Distributed Task Queue Cancellation & State Machine:
1. Cancellation of Pending task (status -> cancelled, lease cleared).
2. Cancellation of Assigned task (status -> cancelled, lease cleared, worker freed).
3. Cancellation of Running task (status -> cancelled, lease cleared, worker freed).
4. Cancellation of Completed task (rejected, status remains completed, success=False).
5. Cancellation of Non-existent task (HTTP 404).
6. Repeated / double / triple cancellation (idempotent behavior, returns 200, status remains cancelled).
7. Database audit log verification (action CANCEL_TASK recorded in logs table with task_id & metadata).
8. Adversarial edge cases:
   - Worker has moved on to a different task: cancelling old task does NOT clear worker's active task lock.
   - High-throughput parallel rapid cancellation (30 concurrent threads).
   - Race condition: Worker lease renewal (/heartbeat) vs Admin cancellation.
   - Race condition: Worker status update (/status) vs Admin cancellation.
"""

import sys
import time
import json
import uuid
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.core.config import settings
from app.db.session import query_one, query_all, execute_write


@pytest.fixture
def client(monkeypatch):
    """TestClient with disabled rate-limit and default project key."""
    monkeypatch.setattr(settings, "SYNC_TOKEN", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    test_client = TestClient(app)
    test_client.headers["X-Project-Key"] = "default"
    return test_client


# ============================================================================
# 1. PENDING TASK CANCELLATION
# ============================================================================
def test_cancel_pending_task_state_and_lease(client):
    """
    Empirical Challenge 1:
    Verify cancellation of a pending task transitions status to 'cancelled'
    and guarantees lease_expires_at is NULL in database.
    """
    unique_id = f"test_pending_{uuid.uuid4().hex[:8]}"
    create_res = client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 10,
        "payload": {"duration": 120}
    })
    assert create_res.status_code == 201, f"Create failed: {create_res.text}"
    created_task = create_res.json()["task"]
    assert created_task["status"] == "pending"

    # Cancel task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data.get("success") is True
    assert cancel_data.get("status") == "cancelled"
    assert cancel_data.get("taskId") == unique_id

    # Verify directly from DB
    row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert row is not None
    assert row["status"] == "cancelled"
    assert row["lease_expires_at"] is None

    # Verify via GET /api/tasks
    list_res = client.get(f"/api/tasks?status=cancelled")
    assert list_res.status_code == 200
    matching = [t for t in list_res.json().get("tasks", []) if t["id"] == unique_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "cancelled"
    assert matching[0]["leaseExpiresAt"] is None


# ============================================================================
# 2. ASSIGNED TASK CANCELLATION & WORKER RELEASE
# ============================================================================
def test_cancel_assigned_task_frees_worker(client):
    """
    Empirical Challenge 2:
    Worker claims task via /poll (status='assigned').
    Cancelling task must clear lease and free worker node.
    """
    worker_id = f"worker_assign_{uuid.uuid4().hex[:6]}"
    unique_id = f"task_assign_{uuid.uuid4().hex[:6]}"

    # Register worker
    reg_res = client.post("/api/workers/register", json={
        "id": worker_id,
        "name": f"Node-{worker_id}",
        "projectKey": "default"
    })
    assert reg_res.status_code == 200

    # Create task with high priority so it is claimed first
    create_res = client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "post",
        "projectKey": "default",
        "priority": 99999,
        "payload": {"content": "Assigned test post"}
    })
    assert create_res.status_code == 201

    # Worker claims task via poll
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["post"]
    })
    assert poll_res.status_code == 200
    claimed = poll_res.json().get("task")
    assert claimed is not None
    assert claimed["id"] == unique_id
    assert claimed["status"] == "assigned"
    assert claimed["leaseExpiresAt"] is not None

    # Set worker current_task_id to simulate worker holding it
    execute_write(
        "UPDATE workers SET current_task_id = ?, updated_at = ? WHERE id = ?",
        (unique_id, int(time.time() * 1000), worker_id)
    )
    w_check = query_one("SELECT current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_check["current_task_id"] == unique_id

    # Admin cancels task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True
    assert cancel_res.json()["status"] == "cancelled"

    # Verify task in DB
    t_row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert t_row["status"] == "cancelled"
    assert t_row["lease_expires_at"] is None

    # Verify worker in DB is freed
    w_row = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    assert w_row["current_task_id"] is None


# ============================================================================
# 3. RUNNING TASK CANCELLATION & WORKER RELEASE
# ============================================================================
def test_cancel_running_task_frees_worker(client):
    """
    Empirical Challenge 3:
    Task is reported as 'running' by worker (worker status becomes 'busy').
    Cancelling must set status='cancelled', lease_expires_at=None, and clear worker current_task_id.
    """
    worker_id = f"worker_running_{uuid.uuid4().hex[:6]}"
    unique_id = f"task_running_{uuid.uuid4().hex[:6]}"

    # Register worker
    client.post("/api/workers/register", json={
        "id": worker_id,
        "name": f"Node-{worker_id}",
        "projectKey": "default"
    })

    # Create task with high priority
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "seed",
        "projectKey": "default",
        "priority": 99999,
        "payload": {"targetUrl": "https://facebook.com/post/1"}
    })

    # Claim task
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["seed"]
    })
    assert poll_res.status_code == 200
    assert poll_res.json()["task"]["id"] == unique_id

    # Worker reports running
    status_res = client.post(f"/api/tasks/{unique_id}/status", json={
        "workerId": worker_id,
        "status": "running",
        "result": {"progress": 25}
    })
    assert status_res.status_code == 200

    # Verify worker is busy with this task
    w_row = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    assert w_row["status"] == "busy"
    assert w_row["current_task_id"] == unique_id

    # Cancel task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True

    # Verify task state
    t_row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert t_row["status"] == "cancelled"
    assert t_row["lease_expires_at"] is None

    # Verify worker freed
    w_freed = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    assert w_freed["current_task_id"] is None


# ============================================================================
# 4. COMPLETED TASK CANCELLATION REJECTION
# ============================================================================
def test_cancel_completed_task_is_rejected(client):
    """
    Empirical Challenge 4:
    A task that has already completed cannot be cancelled.
    Server must respond with success=False, status='completed',
    and the task's database status must remain 'completed'.
    """
    unique_id = f"task_completed_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "post",
        "projectKey": "default",
        "payload": {"content": "Will be completed"}
    })

    # Worker completes task
    status_res = client.post(f"/api/tasks/{unique_id}/status", json={
        "status": "completed",
        "result": {"postId": "fb_123456"}
    })
    assert status_res.status_code == 200

    t_before = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert t_before["status"] == "completed"

    # Attempt to cancel completed task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200
    data = cancel_res.json()
    assert data.get("success") is False
    assert data.get("status") == "completed"
    assert "không thể hủy" in data.get("message", "")

    # Verify DB status is UNTOUCHED
    t_after = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert t_after["status"] == "completed"
    assert t_after["completed_at"] == t_before["completed_at"]


# ============================================================================
# 5. NON-EXISTENT TASK CANCELLATION (404)
# ============================================================================
def test_cancel_nonexistent_task_returns_404(client):
    """
    Empirical Challenge 5:
    Attempting to cancel a non-existent task returns 404 with descriptive detail.
    """
    fake_id = f"nonexistent_{uuid.uuid4().hex}"
    res = client.post(f"/api/tasks/{fake_id}/cancel")
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


# ============================================================================
# 6. IDEMPOTENT DOUBLE / REPEATED CANCELLATION
# ============================================================================
def test_repeated_cancellation_is_idempotent(client):
    """
    Empirical Challenge 6:
    Calling cancel repeatedly on the same task must be idempotent:
    Both calls return 200, status remains 'cancelled', and no server errors occur.
    """
    unique_id = f"task_double_cancel_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "warmup",
        "projectKey": "default",
        "payload": {"duration": 30}
    })

    # First cancellation
    res1 = client.post(f"/api/tasks/{unique_id}/cancel")
    assert res1.status_code == 200
    assert res1.json()["success"] is True
    assert res1.json()["status"] == "cancelled"

    # Second cancellation (idempotent)
    res2 = client.post(f"/api/tasks/{unique_id}/cancel")
    assert res2.status_code == 200
    assert res2.json()["success"] is True
    assert res2.json()["status"] == "cancelled"

    # Third cancellation
    res3 = client.post(f"/api/tasks/{unique_id}/cancel")
    assert res3.status_code == 200
    assert res3.json()["success"] is True
    assert res3.json()["status"] == "cancelled"

    # Verify final DB state
    row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert row["status"] == "cancelled"
    assert row["lease_expires_at"] is None


# ============================================================================
# 7. DATABASE AUDIT LOG VERIFICATION (PENDING & ASSIGNED)
# ============================================================================
def test_cancellation_audit_log_recorded_pending(client):
    """
    Empirical Challenge 7A:
    Cancelling a pending task must write a structured CANCEL_TASK audit entry
    to `logs` table with previousStatus='pending'.
    """
    unique_id = f"task_audit_p_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 1,
        "payload": {"duration": 10}
    })

    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200

    log_row = query_one(
        "SELECT * FROM logs WHERE action = 'CANCEL_TASK' AND entity_id = ? ORDER BY id DESC",
        (unique_id,)
    )
    assert log_row is not None
    assert log_row["entity_type"] == "task"
    details = json.loads(log_row["details"])
    assert details.get("taskId") == unique_id
    assert details.get("previousStatus") == "pending"
    assert "cancelledAt" in details


def test_cancellation_audit_log_recorded_assigned(client):
    """
    Empirical Challenge 7B:
    Cancelling an assigned task must write a structured CANCEL_TASK audit entry
    with previousStatus='assigned' and workerId.
    """
    worker_id = f"worker_log_ass_{uuid.uuid4().hex[:6]}"
    unique_id = f"task_audit_ass_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Audit Worker Assigned"})
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "post",
        "projectKey": "default",
        "priority": 99999,
        "payload": {"content": "Audit check assigned"}
    })
    poll_res = client.post("/api/tasks/poll", json={"workerId": worker_id, "projectKey": "default", "supportedTypes": ["post"]})
    assert poll_res.status_code == 200
    assert poll_res.json()["task"]["id"] == unique_id

    # Cancel task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200

    log_row = query_one(
        "SELECT * FROM logs WHERE action = 'CANCEL_TASK' AND entity_id = ? ORDER BY id DESC",
        (unique_id,)
    )
    assert log_row is not None
    details = json.loads(log_row["details"])
    assert details.get("taskId") == unique_id
    assert details.get("previousStatus") == "assigned"
    assert details.get("workerId") == worker_id


# ============================================================================
# 8. ADVERSARIAL EDGE CASE: WORKER MOVED TO ANOTHER TASK
# ============================================================================
def test_cancel_does_not_clear_worker_if_worker_moved_to_different_task(client):
    """
    Empirical Challenge 8:
    Adversarial verification:
    If worker_1 was previously assigned to Task A, but Task A timed out / was reassigned,
    and worker_1 is now actively running Task B (current_task_id = Task B).
    Cancelling Task A must NOT clear worker_1's current_task_id (Task B)!
    """
    worker_id = f"worker_multi_{uuid.uuid4().hex[:6]}"
    task_a = f"task_old_{uuid.uuid4().hex[:6]}"
    task_b = f"task_active_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Multi Task Worker"})

    # Task A was assigned to worker_id
    now_ms = int(time.time() * 1000)
    execute_write("""
        INSERT INTO tasks (id, task_type, project_key, worker_id, status, priority, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
        VALUES (?, 'post', 'default', ?, 'assigned', 10, '{}', ?, 0, 3, ?, ?)
    """, (task_a, worker_id, now_ms, now_ms, now_ms))

    # Worker has moved on and is now actively executing Task B!
    execute_write("""
        UPDATE workers SET current_task_id = ?, status = 'busy', updated_at = ? WHERE id = ?
    """, (task_b, now_ms, worker_id))

    # Verify worker currently holds task_b
    w_check = query_one("SELECT current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_check["current_task_id"] == task_b

    # Cancel old Task A
    cancel_res = client.post(f"/api/tasks/{task_a}/cancel")
    assert cancel_res.status_code == 200

    # Worker MUST still hold Task B (anti-corruption guarantee)
    w_after = query_one("SELECT current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_after["current_task_id"] == task_b, "Worker current_task_id for Task B was erroneously wiped by cancelling Task A!"


# ============================================================================
# 9. CONCURRENCY & RACE CONDITIONS STRESS TESTS
# ============================================================================
def test_concurrency_rapid_parallel_cancellations(client):
    """
    Empirical Challenge 9A:
    30 concurrent threads simultaneously call POST /api/tasks/{task_id}/cancel.
    Tests SQLite WAL concurrency, lock handling, and determinism under contention.
    All calls must complete cleanly without 500 crashes or sqlite3.OperationalError.
    """
    unique_id = f"task_rapid_cancel_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "warmup",
        "projectKey": "default",
        "payload": {"duration": 180}
    })

    num_threads = 30
    results = []

    def perform_cancel():
        return client.post(f"/api/tasks/{unique_id}/cancel")

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(perform_cancel) for _ in range(num_threads)]
        for f in as_completed(futures):
            res = f.result()
            results.append((res.status_code, res.json()))

    # Verify all requests succeeded
    for status_code, body in results:
        assert status_code == 200, f"Concurrent cancel returned non-200: {status_code}, {body}"
        assert body.get("success") is True
        assert body.get("status") == "cancelled"

    # Database state must be consistent
    row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert row["status"] == "cancelled"
    assert row["lease_expires_at"] is None


def test_concurrency_heartbeat_renewal_vs_cancellation(client):
    """
    Empirical Challenge 9B:
    Worker repeatedly extends lease via POST /api/tasks/{task_id}/heartbeat
    while Admin concurrently sends POST /api/tasks/{task_id}/cancel.
    Verifies that regardless of thread interleaving:
    - No SQLite operational crash occurs.
    - Final state converges predictably.
    """
    worker_id = f"worker_hb_{uuid.uuid4().hex[:6]}"
    unique_id = f"task_hb_race_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "HB Worker"})
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "seed",
        "projectKey": "default",
        "priority": 99999,
        "payload": {"target": "fb.com"}
    })
    client.post("/api/tasks/poll", json={"workerId": worker_id, "projectKey": "default", "supportedTypes": ["seed"]})

    stop_heartbeat = threading.Event()
    hb_results = []
    cancel_result = []

    def worker_heartbeat_loop():
        while not stop_heartbeat.is_set():
            res = client.post(f"/api/tasks/{unique_id}/heartbeat", json={"extendSec": 60})
            hb_results.append(res.status_code)
            time.sleep(0.005)

    def admin_cancel():
        time.sleep(0.02)  # Allow a few heartbeats to fire
        res = client.post(f"/api/tasks/{unique_id}/cancel")
        cancel_result.append((res.status_code, res.json()))
        stop_heartbeat.set()

    with ThreadPoolExecutor(max_workers=5) as executor:
        hb_future = executor.submit(worker_heartbeat_loop)
        cancel_future = executor.submit(admin_cancel)
        hb_future.result()
        cancel_future.result()

    # Cancel request must have succeeded
    assert len(cancel_result) == 1
    assert cancel_result[0][0] == 200
    assert cancel_result[0][1].get("success") is True

    # No 500 error during heartbeats
    for code in hb_results:
        assert code in (200, 400, 404)

    # In DB: task status must be 'cancelled'
    row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert row["status"] == "cancelled"


def test_concurrency_worker_status_update_vs_cancellation(client):
    """
    Empirical Challenge 9C:
    Race condition where worker tries to complete/fail a task right as Admin cancels it.
    Verifies that concurrent status updates and cancellations do not corrupt the database.
    """
    unique_id = f"task_race_status_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "warmup",
        "projectKey": "default",
        "payload": {"duration": 60}
    })

    results = []

    def do_cancel():
        res = client.post(f"/api/tasks/{unique_id}/cancel")
        results.append(("cancel", res.status_code, res.json()))

    def do_status_update():
        res = client.post(f"/api/tasks/{unique_id}/status", json={
            "status": "completed",
            "result": {"summary": "Done"}
        })
        results.append(("status", res.status_code, res.json()))

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_cancel)
        f2 = executor.submit(do_status_update)
        f1.result()
        f2.result()

    # Both HTTP calls must return 200 without database deadlocks
    for op, code, body in results:
        assert code == 200, f"Op {op} failed with code {code}: {body}"

    # Verify task is in a valid terminal state ('cancelled' or 'completed')
    row = query_one("SELECT * FROM tasks WHERE id = ?", (unique_id,))
    assert row["status"] in ("cancelled", "completed")
    # Lease must be NULL regardless of which won the race
    assert row["lease_expires_at"] is None


# ============================================================================
# 10. ADVANCED ADVERSARIAL CASES: QUEUE SAFETY & MULTI-TENANCY
# ============================================================================
def test_poll_never_claims_cancelled_task(client):
    """
    Empirical Challenge 10A:
    Ensure that once a task is cancelled, worker poll calls NEVER claim it,
    even if the task has maximum priority (999999) and scheduled_time in the past.
    """
    worker_id = f"worker_poll_safe_{uuid.uuid4().hex[:6]}"
    task_id = f"task_poll_safe_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Safe Worker"})

    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 999999,
        "scheduledTime": int(time.time() * 1000) - 10000,
        "payload": {"duration": 30}
    })

    # Cancel task immediately
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200

    # Worker attempts to poll
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["warmup"]
    })
    assert poll_res.status_code == 200
    claimed_task = poll_res.json().get("task")

    # If a task was returned, it must NOT be the cancelled task!
    if claimed_task:
        assert claimed_task["id"] != task_id, f"Cancelled task {task_id} was claimed by worker!"


def test_cancel_respects_project_key_in_audit_log(client):
    """
    Empirical Challenge 10B:
    Multi-tenant isolation: when a task belonging to 'project_omega' is cancelled,
    the CANCEL_TASK audit log in DB must accurately record 'project_omega'.
    """
    proj_key = f"proj_omega_{uuid.uuid4().hex[:6]}"
    task_id = f"task_omega_{uuid.uuid4().hex[:6]}"

    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "seed",
        "projectKey": proj_key,
        "payload": {"target": "omega"}
    })

    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200

    log_row = query_one(
        "SELECT * FROM logs WHERE action = 'CANCEL_TASK' AND entity_id = ? ORDER BY id DESC",
        (task_id,)
    )
    assert log_row is not None
    assert log_row["project_key"] == proj_key, f"Expected project_key {proj_key}, got {log_row['project_key']}"


def test_cancel_failed_task_transitions_to_cancelled(client):
    """
    Empirical Challenge 10C:
    An admin cancelling a previously failed task transitions status to 'cancelled',
    clearing any error state or lease.
    """
    unique_id = f"task_failed_{uuid.uuid4().hex[:6]}"

    client.post("/api/tasks", json={
        "id": unique_id,
        "taskType": "post",
        "projectKey": "default",
        "maxRetries": 1,
        "payload": {"content": "Fail test"}
    })

    # Worker reports failure, exhausting retries
    client.post(f"/api/tasks/{unique_id}/status", json={
        "status": "failed",
        "error": "Account checkpointed"
    })

    row_before = query_one("SELECT status FROM tasks WHERE id = ?", (unique_id,))
    assert row_before["status"] == "failed"

    # Admin cancels the failed task
    cancel_res = client.post(f"/api/tasks/{unique_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True
    assert cancel_res.json()["status"] == "cancelled"

    row_after = query_one("SELECT status, lease_expires_at FROM tasks WHERE id = ?", (unique_id,))
    assert row_after["status"] == "cancelled"
    assert row_after["lease_expires_at"] is None


def test_high_load_batch_parallel_cancellations(client):
    """
    Empirical Challenge 10D:
    High-load stress: Enqueue 50 distinct tasks and cancel all 50 in parallel threads.
    Verifies SQLite WAL concurrency under heavy concurrent write operations.
    """
    batch_size = 50
    task_ids = [f"task_batch_cancel_{i}_{uuid.uuid4().hex[:4]}" for i in range(batch_size)]

    # Create 50 tasks
    for tid in task_ids:
        client.post("/api/tasks", json={
            "id": tid,
            "taskType": "warmup",
            "projectKey": "default",
            "payload": {"batchIndex": tid}
        })

    # Cancel all 50 concurrently
    def cancel_single_task(tid):
        return client.post(f"/api/tasks/{tid}/cancel")

    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(cancel_single_task, tid): tid for tid in task_ids}
        for future in as_completed(future_map):
            res = future.result()
            assert res.status_code == 200
            assert res.json().get("success") is True
            assert res.json().get("status") == "cancelled"

    # Verify all 50 in DB
    placeholders = ", ".join(["?"] * len(task_ids))
    rows = query_all(
        f"SELECT id, status, lease_expires_at FROM tasks WHERE id IN ({placeholders})",
        tuple(task_ids)
    )
    assert len(rows) == batch_size
    for r in rows:
        assert r["status"] == "cancelled"
        assert r["lease_expires_at"] is None

