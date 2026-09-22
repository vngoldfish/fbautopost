"""
tests/test_challenger_m5_gate2_lease_affinity.py
Empirical Challenger test suite for Milestone 5 Phase 2 Gate 2:
Verifying BUG-T5-01 fix, expired lease reclaim, and worker affinity guarantees under adversarial conditions.
"""

import sys
import time
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from app.db.session import execute_write, query_one
from tests.e2e.conftest import DEFAULT_SYNC_TOKEN, DEFAULT_PROJECT_KEY, E2EClient


@pytest.fixture
def client():
    return E2EClient(default_token=DEFAULT_SYNC_TOKEN, default_project=DEFAULT_PROJECT_KEY)


def test_challenger_pending_task_worker_affinity_isolation(client):
    """
    Test that a pending task with a specified worker_id can ONLY be claimed
    by that specific worker, and never by any other worker.
    """
    proj = f"proj_aff_test_{int(time.time()*1000)}"
    task_id = f"task_aff_targeted_{int(time.time()*1000)}"

    # 1. Create a task explicitly targeted to worker_alpha
    res = client.post("/api/tasks", json={
        "id": task_id,
        "type": "post",
        "projectKey": proj,
        "workerId": "worker_alpha",
        "payload": {"content": "Affinity Targeted Task"}
    })
    assert res.status_code == 201

    # 2. Worker beta attempts to poll - MUST receive None
    res_beta = client.post("/api/tasks/poll", json={
        "workerId": "worker_beta",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_beta.status_code == 200
    assert res_beta.json().get("task") is None, "Worker beta illegally claimed task targeted to worker alpha!"

    # 3. Worker gamma attempts to poll - MUST receive None
    res_gamma = client.post("/api/tasks/poll", json={
        "workerId": "worker_gamma",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_gamma.status_code == 200
    assert res_gamma.json().get("task") is None, "Worker gamma illegally claimed task targeted to worker alpha!"

    # 4. Worker alpha polls - MUST successfully claim the task
    res_alpha = client.post("/api/tasks/poll", json={
        "workerId": "worker_alpha",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_alpha.status_code == 200
    claimed = res_alpha.json().get("task")
    assert claimed is not None, "Worker alpha failed to claim its targeted task!"
    assert claimed["id"] == task_id
    assert claimed["workerId"] == "worker_alpha"
    assert claimed["status"] == "assigned"


def test_challenger_active_lease_protection(client):
    """
    Test that while a lease is active (unexpired), no other worker can reclaim it.
    """
    proj = f"proj_active_{int(time.time()*1000)}"
    task_id = f"task_active_{int(time.time()*1000)}"
    now_ms = int(time.time() * 1000)

    # Insert a task assigned to worker_alpha with active lease (expires in 60s)
    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, worker_id, status, payload,
            claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
        ) VALUES (?, 'post', ?, 'worker_alpha', 'assigned', '{}', ?, ?, ?, 0, ?, ?)
    """, (task_id, proj, now_ms, now_ms + 60000, now_ms, now_ms, now_ms))

    # Worker beta polls - MUST NOT steal active lease
    res_beta = client.post("/api/tasks/poll", json={
        "workerId": "worker_beta",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_beta.status_code == 200
    assert res_beta.json().get("task") is None, "Worker beta stole an active lease!"


def test_challenger_expired_lease_standby_reclaim(client):
    """
    Test that when worker_alpha crashes and its lease expires,
    standby worker_beta can seamlessly reclaim it.
    """
    proj = f"proj_reclaim_{int(time.time()*1000)}"
    task_id = f"task_reclaim_{int(time.time()*1000)}"
    now_ms = int(time.time() * 1000)

    # Insert an assigned task with expired lease (expired 10s ago)
    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, worker_id, status, payload,
            claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
        ) VALUES (?, 'post', ?, 'crashed_alpha', 'assigned', '{}', ?, ?, ?, 0, ?, ?)
    """, (task_id, proj, now_ms - 70000, now_ms - 10000, now_ms - 70000, now_ms - 70000, now_ms - 70000))

    # Standby worker_beta polls
    res_beta = client.post("/api/tasks/poll", json={
        "workerId": "standby_beta",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_beta.status_code == 200
    claimed = res_beta.json().get("task")
    assert claimed is not None, "Standby worker_beta failed to reclaim expired lease!"
    assert claimed["id"] == task_id
    assert claimed["workerId"] == "standby_beta"
    assert claimed["leaseExpiresAt"] > int(time.time() * 1000)

    # Check DB state
    row = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    assert row["worker_id"] == "standby_beta"
    assert row["status"] == "assigned"


def test_challenger_account_affinity_quarantine_and_isolation(client):
    """
    Test that account affinity is maintained during polling:
    A task linked to an account assigned to Worker A cannot be claimed by Worker B,
    even if Worker B polls when the task is pending or expired, UNLESS Worker B is assigned that account.
    """
    proj = f"proj_acc_aff_{int(time.time()*1000)}"
    acc_id = f"acc_pinned_{int(time.time()*1000)}"
    task_id = f"task_acc_{int(time.time()*1000)}"
    now_ms = int(time.time() * 1000)

    # Create account bound to worker_alpha
    execute_write("""
        INSERT INTO accounts (id, target_id, name, account_type, project_key, worker_id, status, created_at, updated_at)
        VALUES (?, ?, 'Pinned Alpha Acc', 'profile', ?, 'worker_alpha', 'active', ?, ?)
    """, (acc_id, acc_id, proj, now_ms, now_ms))

    # Create task linked to this account
    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, account_id, status, payload,
            scheduled_time, retry_count, created_at, updated_at
        ) VALUES (?, 'post', ?, ?, 'pending', '{}', ?, 0, ?, ?)
    """, (task_id, proj, acc_id, now_ms, now_ms, now_ms))

    # Worker beta (without assigned accounts) attempts to poll - MUST be blocked by affinity
    res_beta = client.post("/api/tasks/poll", json={
        "workerId": "worker_beta",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_beta.status_code == 200
    assert res_beta.json().get("task") is None, "Worker beta claimed a task bound to worker alpha's account!"

    # Worker alpha polls - successfully claims
    res_alpha = client.post("/api/tasks/poll", json={
        "workerId": "worker_alpha",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res_alpha.status_code == 200
    claimed = res_alpha.json().get("task")
    assert claimed is not None
    assert claimed["id"] == task_id
    assert claimed["workerId"] == "worker_alpha"


def test_challenger_concurrent_reclaim_stress_20_workers(client):
    """
    Adversarial stress: 20 standby workers all contest 1 expired lease simultaneously.
    Exactly 1 worker claims, 19 receive None. Zero database locking errors.
    """
    proj = f"proj_stress_{int(time.time()*1000)}"
    task_id = f"task_stress_{int(time.time()*1000)}"
    now_ms = int(time.time() * 1000)

    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, worker_id, status, payload,
            claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
        ) VALUES (?, 'post', ?, 'dead_worker_42', 'running', '{}', ?, ?, ?, 0, ?, ?)
    """, (task_id, proj, now_ms - 80000, now_ms - 5000, now_ms - 80000, now_ms - 80000, now_ms - 80000))

    num_workers = 20
    barrier = threading.Barrier(num_workers)
    results = []
    errors = []

    def worker_run(idx):
        worker_id = f"stress_worker_{idx}_{int(time.time()*1000)}"
        try:
            barrier.wait(timeout=5.0)
            res = client.post("/api/tasks/poll", json={
                "workerId": worker_id,
                "supportedTypes": ["post"],
                "projectKey": proj
            }, headers={"X-Project-Key": proj})
            if res.status_code == 200:
                results.append((worker_id, res.json().get("task")))
            else:
                errors.append((worker_id, res.status_code, res.text))
        except Exception as e:
            errors.append((worker_id, str(e)))

    threads = [threading.Thread(target=worker_run, args=(i,)) for i in range(num_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Thread errors: {errors}"
    claimed_list = [t for _, t in results if t is not None and t.get("id") == task_id]
    assert len(claimed_list) == 1, f"Expected exactly 1 claim, got {len(claimed_list)}"
    assert claimed_list[0]["workerId"] != "dead_worker_42"
    assert claimed_list[0]["leaseExpiresAt"] > int(time.time() * 1000)


def test_challenger_multi_hop_failover_reclaim(client):
    """
    Test multi-hop failover:
    Worker 1 claims and crashes (lease expires) ->
    Worker 2 reclaims and crashes (lease expires) ->
    Worker 3 reclaims successfully.
    """
    proj = f"proj_multihop_{int(time.time()*1000)}"
    task_id = f"task_multihop_{int(time.time()*1000)}"
    now_ms = int(time.time() * 1000)

    # 1. Initially assigned to Worker 1 with expired lease
    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, worker_id, status, payload,
            claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
        ) VALUES (?, 'post', ?, 'node_1', 'assigned', '{}', ?, ?, ?, 0, ?, ?)
    """, (task_id, proj, now_ms - 150000, now_ms - 90000, now_ms - 150000, now_ms - 150000, now_ms - 150000))

    # 2. Worker 2 claims it (reclaim hop 1)
    res2 = client.post("/api/tasks/poll", json={
        "workerId": "node_2",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res2.status_code == 200
    claimed2 = res2.json().get("task")
    assert claimed2 is not None
    assert claimed2["workerId"] == "node_2"

    # Simulate Worker 2 crashing and its lease expiring
    execute_write("""
        UPDATE tasks SET lease_expires_at = ? WHERE id = ?
    """, (now_ms - 1000, task_id))

    # 3. Worker 3 claims it (reclaim hop 2)
    res3 = client.post("/api/tasks/poll", json={
        "workerId": "node_3",
        "supportedTypes": ["post"],
        "projectKey": proj
    }, headers={"X-Project-Key": proj})
    assert res3.status_code == 200
    claimed3 = res3.json().get("task")
    assert claimed3 is not None
    assert claimed3["workerId"] == "node_3"
    assert claimed3["leaseExpiresAt"] > int(time.time() * 1000)

    # Verify DB final state
    row = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    assert row["worker_id"] == "node_3"
    assert row["status"] == "assigned"

