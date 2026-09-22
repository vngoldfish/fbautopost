"""
tests/test_challenger_m4_gate2_tasks_stress.py
Empirical Challenger 1 Stress Suite for Milestone 4 Gate 2 (challenger_m4_gate2_1)

Validates:
1. GET /api/tasks:
   - Chronological ordering (created_at DESC) ensures newest tasks appear first regardless of priority.
   - GET /api/tasks?taskId={id} and ?id={id} returns exactly 1 item under high load (thousands of tasks).
   - Single task endpoint GET /api/tasks/{task_id} returns 200 for existing and 404 for non-existent.
2. POST /api/tasks/{task_id}/heartbeat:
   - Attempting to heartbeat a cancelled task returns HTTP 400.
   - Attempting to heartbeat a completed task returns HTTP 400.
   - Attempting to heartbeat a failed task returns HTTP 400.
   - Valid running task successfully extends lease expiration.
3. POST /api/tasks/{task_id}/cancel:
   - Cancelling a running task resets a busy worker's status to 'online' and clears current_task_id.
   - Cancelling preserves non-busy worker status (e.g. 'paused') while clearing current_task_id.
"""

import sys
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.core.config import settings
from app.db.session import query_one, query_all, execute_write, transaction


@pytest.fixture
def client(monkeypatch):
    """TestClient with disabled rate-limit and default project key."""
    monkeypatch.setattr(settings, "SYNC_TOKEN", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    test_client = TestClient(app)
    test_client.headers["X-Project-Key"] = "default"
    return test_client


# ============================================================================
# 1. GET /api/tasks ORDERING & FILTERING EMPIRICAL STRESS TESTS
# ============================================================================

def test_chronological_ordering_over_priority(client):
    """
    Empirical Challenge 1A:
    Create priority-10, priority-5, and priority-1 tasks sequentially.
    Verify that chronological ordering (created_at DESC) ensures newest tasks
    appear first in GET /api/tasks, regardless of their priority.
    """
    # Create Task 1: Priority 10 (Created first, oldest)
    t1_id = f"stress_ord_p10_{uuid.uuid4().hex[:6]}"
    r1 = client.post("/api/tasks", json={
        "id": t1_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 10,
        "payload": {"seq": 1}
    })
    assert r1.status_code == 201

    time.sleep(0.01)  # Ensure distinct millisecond timestamp

    # Create Task 2: Priority 5 (Created second)
    t2_id = f"stress_ord_p5_{uuid.uuid4().hex[:6]}"
    r2 = client.post("/api/tasks", json={
        "id": t2_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 5,
        "payload": {"seq": 2}
    })
    assert r2.status_code == 201

    time.sleep(0.01)  # Ensure distinct millisecond timestamp

    # Create Task 3: Priority 1 (Created third, newest)
    t3_id = f"stress_ord_p1_{uuid.uuid4().hex[:6]}"
    r3 = client.post("/api/tasks", json={
        "id": t3_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 1,
        "payload": {"seq": 3}
    })
    assert r3.status_code == 201

    # Fetch recent tasks
    list_res = client.get("/api/tasks?limit=50")
    assert list_res.status_code == 200
    tasks = list_res.json().get("tasks", [])

    # Find the positions of all 3 tasks in the returned list
    task_ids = [t["id"] for t in tasks]
    assert t1_id in task_ids, f"{t1_id} missing from list"
    assert t2_id in task_ids, f"{t2_id} missing from list"
    assert t3_id in task_ids, f"{t3_id} missing from list"

    idx_t1 = task_ids.index(t1_id)
    idx_t2 = task_ids.index(t2_id)
    idx_t3 = task_ids.index(t3_id)

    # In created_at DESC order:
    # t3 (newest, created last) must appear before t2
    # t2 must appear before t1 (oldest, created first)
    assert idx_t3 < idx_t2, (
        f"Chronological ordering violation: t3 (prio 1, newest) index {idx_t3} "
        f"should be before t2 (prio 5) index {idx_t2}"
    )
    assert idx_t2 < idx_t1, (
        f"Chronological ordering violation: t2 (prio 5) index {idx_t2} "
        f"should be before t1 (prio 10, oldest) index {idx_t1}"
    )


def test_chronological_ordering_tie_breaking(client):
    """
    Empirical Challenge 1B:
    When created_at is identical, priority DESC breaks the tie.
    """
    fixed_ts = int(time.time() * 1000) + 500000  # distinct future timestamp
    tie_low = f"tie_low_{uuid.uuid4().hex[:6]}"
    tie_high = f"tie_high_{uuid.uuid4().hex[:6]}"

    execute_write("""
        INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, created_at, updated_at)
        VALUES (?, 'warmup', 'default', 1, 'pending', '{}', ?, ?, ?)
    """, (tie_low, fixed_ts, fixed_ts, fixed_ts))

    execute_write("""
        INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, created_at, updated_at)
        VALUES (?, 'warmup', 'default', 10, 'pending', '{}', ?, ?, ?)
    """, (tie_high, fixed_ts, fixed_ts, fixed_ts))

    list_res = client.get("/api/tasks?limit=50")
    assert list_res.status_code == 200
    task_ids = [t["id"] for t in list_res.json().get("tasks", [])]

    assert tie_high in task_ids
    assert tie_low in task_ids
    assert task_ids.index(tie_high) < task_ids.index(tie_low), (
        "Tie-breaker failure: higher priority task should precede lower priority when created_at is identical"
    )


def test_get_tasks_filter_with_thousands_of_tasks(client):
    """
    Empirical Challenge 1C:
    Insert 2,000 tasks into the database.
    Verify that GET /api/tasks?taskId={id} and GET /api/tasks?id={id}
    returns exactly 1 matching item, avoiding query truncation or offset drowning.
    """
    batch_prefix = f"load_{uuid.uuid4().hex[:4]}"
    num_flood_tasks = 2000
    now_ms = int(time.time() * 1000)

    # Insert 2,000 flood tasks in a single fast transaction
    with transaction() as conn:
        flood_rows = [
            (f"{batch_prefix}_{i}", "post", "default", 10, "pending", "{}", now_ms - (i * 10), now_ms - (i * 10), now_ms - (i * 10))
            for i in range(num_flood_tasks)
        ]
        conn.executemany("""
            INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, flood_rows)

    # Insert 1 needle task with low priority and old timestamp
    needle_id = f"needle_{uuid.uuid4().hex[:8]}"
    needle_created = now_ms - 9999999
    execute_write("""
        INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, created_at, updated_at)
        VALUES (?, 'seed', 'default', 1, 'pending', '{}', ?, ?, ?)
    """, (needle_id, needle_created, needle_created, needle_created))

    # Query by taskId
    res_task_id = client.get(f"/api/tasks?taskId={needle_id}")
    assert res_task_id.status_code == 200
    data1 = res_task_id.json()
    assert data1.get("total") == 1
    assert len(data1.get("tasks", [])) == 1
    assert data1["tasks"][0]["id"] == needle_id
    assert data1["tasks"][0]["priority"] == 1

    # Query by id alias
    res_alias_id = client.get(f"/api/tasks?id={needle_id}")
    assert res_alias_id.status_code == 200
    data2 = res_alias_id.json()
    assert data2.get("total") == 1
    assert len(data2.get("tasks", [])) == 1
    assert data2["tasks"][0]["id"] == needle_id

    # Non-existent ID returns exactly 0
    res_none = client.get("/api/tasks?taskId=nonexistent_synthetic_id_99999")
    assert res_none.status_code == 200
    assert res_none.json().get("total") == 0
    assert len(res_none.json().get("tasks", [])) == 0


def test_single_task_lookup_endpoint(client):
    """
    Empirical Challenge 1D:
    Verify GET /api/tasks/{task_id} returns 200 with complete task object
    for an existing task, and returns 404 for a non-existent task.
    """
    task_id = f"task_lookup_{uuid.uuid4().hex[:6]}"
    create_res = client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 7,
        "payload": {"message": "Single lookup test"}
    })
    assert create_res.status_code == 201

    # Valid lookup
    get_res = client.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200
    body = get_res.json()
    assert body.get("success") is True
    assert body.get("task") is not None
    assert body["task"]["id"] == task_id
    assert body["task"]["type"] == "warmup"
    assert body["task"]["priority"] == 7
    assert body["task"]["payload"] == {"message": "Single lookup test"}

    # Non-existent lookup
    fake_id = f"fake_{uuid.uuid4().hex}"
    err_res = client.get(f"/api/tasks/{fake_id}")
    assert err_res.status_code == 404
    err_body = err_res.json()
    assert "detail" in err_body
    assert "not found" in err_body["detail"].lower()


# ============================================================================
# 2. POST /api/tasks/{task_id}/heartbeat EMPIRICAL STRESS TESTS
# ============================================================================

def test_heartbeat_rejected_on_cancelled_task(client):
    """
    Empirical Challenge 2A:
    Attempting to heartbeat / extend lease on a cancelled task returns HTTP 400
    and does not update lease_expires_at.
    """
    task_id = f"hb_cancel_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 5
    })

    # Cancel task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json().get("status") == "cancelled"

    # Attempt heartbeat
    hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 60})
    assert hb_res.status_code == 400
    assert "cannot extend lease" in hb_res.json().get("detail", "").lower()

    # Verify DB lease is still NULL
    row = query_one("SELECT lease_expires_at, status FROM tasks WHERE id = ?", (task_id,))
    assert row["status"] == "cancelled"
    assert row["lease_expires_at"] is None


def test_heartbeat_rejected_on_completed_task(client):
    """
    Empirical Challenge 2B:
    Attempting to heartbeat / extend lease on a completed task returns HTTP 400.
    """
    task_id = f"hb_complete_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "post",
        "projectKey": "default",
        "priority": 5
    })

    # Complete task
    stat_res = client.post(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "result": {"url": "https://facebook.com/123"}
    })
    assert stat_res.status_code == 200

    # Attempt heartbeat
    hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 60})
    assert hb_res.status_code == 400
    assert "cannot extend lease" in hb_res.json().get("detail", "").lower()
    assert "completed" in hb_res.json().get("detail", "").lower()


def test_heartbeat_rejected_on_failed_task(client):
    """
    Empirical Challenge 2C:
    Attempting to heartbeat / extend lease on a failed task returns HTTP 400.
    """
    task_id = f"hb_failed_{uuid.uuid4().hex[:6]}"
    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "post",
        "projectKey": "default",
        "maxRetries": 0
    })

    # Fail task
    stat_res = client.post(f"/api/tasks/{task_id}/status", json={
        "status": "failed",
        "error": "Fatal login error"
    })
    assert stat_res.status_code == 200

    # Attempt heartbeat
    hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 60})
    assert hb_res.status_code == 400
    assert "cannot extend lease" in hb_res.json().get("detail", "").lower()
    assert "failed" in hb_res.json().get("detail", "").lower()


def test_heartbeat_valid_running_task_extends_lease(client):
    """
    Empirical Challenge 2D:
    Valid running tasks can successfully extend lease lock duration.
    """
    worker_id = f"worker_hb_valid_{uuid.uuid4().hex[:6]}"
    task_id = f"task_hb_valid_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Valid HB Worker"})
    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "seed",
        "projectKey": "default",
        "priority": 99999
    })

    # Worker claims task via poll
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["seed"]
    })
    assert poll_res.status_code == 200
    claimed = poll_res.json().get("task")
    assert claimed is not None
    assert claimed["id"] == task_id
    initial_lease = claimed["leaseExpiresAt"]

    # Worker transitions task to running
    client.post(f"/api/tasks/{task_id}/status", json={
        "workerId": worker_id,
        "status": "running"
    })

    time.sleep(0.05)

    # Worker calls heartbeat with 120s extension
    extend_sec = 120
    now_estimate = int(time.time() * 1000)
    hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": extend_sec})
    assert hb_res.status_code == 200
    hb_data = hb_res.json()
    assert hb_data.get("success") is True
    assert hb_data.get("taskId") == task_id
    new_lease = hb_data.get("leaseExpiresAt")
    assert new_lease is not None
    assert new_lease >= now_estimate + (extend_sec * 1000) - 1000

    # Verify DB reflects updated lease
    row = query_one("SELECT lease_expires_at, status FROM tasks WHERE id = ?", (task_id,))
    assert row["status"] == "running"
    assert row["lease_expires_at"] == new_lease


# ============================================================================
# 3. POST /api/tasks/{task_id}/cancel WORKER STATE RESET STRESS TESTS
# ============================================================================

def test_cancel_running_task_resets_busy_worker_status_to_online(client):
    """
    Empirical Challenge 3A:
    Cancelling a running task resets worker status from 'busy' to 'online'
    and clears current_task_id.
    """
    worker_id = f"worker_busy_reset_{uuid.uuid4().hex[:6]}"
    task_id = f"task_busy_reset_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Cancel Test Node"})
    client.post("/api/tasks", json={
        "id": task_id,
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 99999
    })

    client.post("/api/tasks/poll", json={"workerId": worker_id, "projectKey": "default", "supportedTypes": ["warmup"]})
    client.post(f"/api/tasks/{task_id}/status", json={"workerId": worker_id, "status": "running"})

    # Verify worker is busy
    w_busy = query_one("SELECT status, current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_busy["status"] == "busy"
    assert w_busy["current_task_id"] == task_id

    # Admin cancels task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json().get("success") is True
    assert cancel_res.json().get("status") == "cancelled"

    # Verify worker is now online and freed
    w_freed = query_one("SELECT status, current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_freed["status"] == "online", f"Expected worker status 'online', got '{w_freed['status']}'"
    assert w_freed["current_task_id"] is None

    # Verify via GET /api/workers
    workers_res = client.get("/api/workers")
    assert workers_res.status_code == 200
    node = next((w for w in workers_res.json().get("workers", []) if w["id"] == worker_id), None)
    assert node is not None
    assert node["status"] == "online"
    assert node["currentTaskId"] is None


def test_cancel_running_task_preserves_non_busy_worker_state(client):
    """
    Empirical Challenge 3B:
    If a worker status was 'paused' or 'error' (non-busy) when a task is cancelled,
    the task cancellation MUST clear current_task_id but MUST NOT overwrite 'paused' with 'online'.
    """
    worker_id = f"worker_paused_{uuid.uuid4().hex[:6]}"
    task_id = f"task_paused_{uuid.uuid4().hex[:6]}"

    client.post("/api/workers/register", json={"id": worker_id, "name": "Paused Node"})

    # Set worker to paused and assign task
    now_ms = int(time.time() * 1000)
    execute_write("""
        INSERT INTO tasks (id, task_type, project_key, worker_id, priority, status, payload, scheduled_time, created_at, updated_at)
        VALUES (?, 'warmup', 'default', ?, 1, 'assigned', '{}', ?, ?, ?)
    """, (task_id, worker_id, now_ms, now_ms, now_ms))

    execute_write("""
        UPDATE workers SET status = 'paused', current_task_id = ? WHERE id = ?
    """, (task_id, worker_id))

    w_before = query_one("SELECT status, current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_before["status"] == "paused"
    assert w_before["current_task_id"] == task_id

    # Admin cancels task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200

    # Worker status must remain 'paused', but current_task_id must be cleared
    w_after = query_one("SELECT status, current_task_id FROM workers WHERE id = ?", (worker_id,))
    assert w_after["status"] == "paused", f"Expected status 'paused' to be preserved, got '{w_after['status']}'"
    assert w_after["current_task_id"] is None
