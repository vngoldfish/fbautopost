"""
fbauto-backend-python/tests/test_challenger_m2_2.py
Milestone 2 Adversarial & Empirical Test Suite by Challenger 2.

Covers:
1. Account Health Transitions ('checkpoint', 'expired', 'locked', 'logged_out') & Immediate Task Quarantine
2. Account Health Restoration ('live', 'active', 'healthy', 'ok') & Queue Task Claiming
3. Worker Account Assignment Two-Way Sync (PUT /api/workers/{id}/accounts and POST /api/workers/{id}/assign)
4. Worker Deletion & Relational NULL Unassignment (DELETE /api/workers/{id})
5. Adversarial Edge Cases & Concurrency Stress (Cross-account isolation, alias shapes, 404 boundaries)
"""

import os
import sys
import time
import json
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.db.session import query_one, query_all, execute_write

from app.core.rate_limiter import rate_limiter

client = TestClient(app)
AUTH_HEADERS = {
    "X-Sync-Token": "fbauto_sync_secret_token_prod_2026",
    "X-Project-Key": "proj_challenger_m2_2"
}


def _unique_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


@pytest.fixture(autouse=True)
def clean_challenger_state():
    """Resets rate limiter and purges test tasks before and after each test."""
    with rate_limiter._lock:
        rate_limiter._history.clear()
    yield
    with rate_limiter._lock:
        rate_limiter._history.clear()
    try:
        execute_write("DELETE FROM tasks WHERE project_key LIKE 'proj_challenger_m2_2%' OR project_key LIKE 'proj_conc%'")
        execute_write("DELETE FROM tasks WHERE id LIKE 'task_%_test%' OR id LIKE 'task_%_lifecycle%'")
    except Exception:
        pass


# ==============================================================================
# SECTION 1: ACCOUNT HEALTH TRANSITIONS & TASK QUARANTINE
# ==============================================================================

class TestAccountHealthTransitionsAndQuarantine:
    """Empirical verification of account health transitions and active task quarantine."""

    def test_checkpoint_transition_quarantines_active_tasks(self):
        """
        Verify setting health to 'checkpoint' cancels pending, assigned, and running tasks,
        clears lease_expires_at, records error, while preserving completed and failed tasks.
        """
        now = int(time.time() * 1000)
        acc_id = _unique_id("acc_cp")
        target_id = _unique_id("fb_cp")

        # 1. Create target account
        create_res = client.post("/api/accounts", json={
            "id": acc_id,
            "targetId": target_id,
            "name": "Checkpoint Quarantine Account",
            "accessToken": "token_cp_test",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)
        assert create_res.status_code == 201

        # 2. Create another unrelated account to verify blast-radius isolation
        other_acc_id = _unique_id("acc_other")
        client.post("/api/accounts", json={
            "id": other_acc_id,
            "name": "Isolated Account",
            "accessToken": "token_other",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        # 3. Create tasks in various states for target account
        test_tasks = {
            "pending": _unique_id("task_pend"),
            "assigned": _unique_id("task_asgn"),
            "running": _unique_id("task_run"),
            "completed": _unique_id("task_comp"),
            "failed": _unique_id("task_fail"),
        }
        for status_val, tid in test_tasks.items():
            lease = (now + 60000) if status_val in ["assigned", "running"] else None
            execute_write("""
                INSERT INTO tasks (
                    id, task_type, project_key, account_id, status, payload,
                    scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at
                ) VALUES (?, 'post', 'proj_challenger_m2_2', ?, ?, '{}', ?, 0, 3, ?, ?, ?)
            """, (tid, acc_id, status_val, now, lease, now, now))

        # Also create a pending task for the other account
        other_tid = _unique_id("task_other")
        execute_write("""
            INSERT INTO tasks (
                id, task_type, project_key, account_id, status, payload,
                scheduled_time, retry_count, max_retries, created_at, updated_at
            ) VALUES (?, 'post', 'proj_challenger_m2_2', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (other_tid, other_acc_id, now, now, now))

        # 4. Trigger checkpoint health transition
        cp_res = client.post(f"/api/accounts/{acc_id}/health", json={
            "healthStatus": "checkpoint",
            "checkpointType": "2fa_sms",
            "message": "Security checkpoint triggered"
        }, headers=AUTH_HEADERS)
        assert cp_res.status_code == 200
        data = cp_res.json()
        assert data["status"] == "checkpoint"
        assert data["healthStatus"] == "checkpoint"
        assert data["account"]["cookieStatus"] == "invalid"

        # 5. Verify active tasks for target account were quarantined
        for status_val in ["pending", "assigned", "running"]:
            row = query_one("SELECT status, lease_expires_at, last_error FROM tasks WHERE id = ?", (test_tasks[status_val],))
            assert row["status"] == "cancelled", f"Task {test_tasks[status_val]} ({status_val}) should be cancelled"
            assert row["lease_expires_at"] is None, f"Task {test_tasks[status_val]} lease should be cleared"
            assert "quarantined" in (row["last_error"] or "").lower()

        # 6. Verify completed and failed tasks were not overwritten
        row_comp = query_one("SELECT status FROM tasks WHERE id = ?", (test_tasks["completed"],))
        assert row_comp["status"] == "completed"

        row_fail = query_one("SELECT status FROM tasks WHERE id = ?", (test_tasks["failed"],))
        assert row_fail["status"] == "failed"

        # 7. Verify other account's task was NOT touched (blast-radius safety)
        row_other = query_one("SELECT status FROM tasks WHERE id = ?", (other_tid,))
        assert row_other["status"] == "pending"

    def test_expired_transition_quarantines_tasks(self):
        """Verify setting health to 'expired' immediately quarantines pending and running tasks."""
        now = int(time.time() * 1000)
        acc_id = _unique_id("acc_exp")

        client.post("/api/accounts", json={
            "id": acc_id,
            "name": "Token Expired Account",
            "accessToken": "exp_tok",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        tid = _unique_id("task_exp")
        execute_write("""
            INSERT INTO tasks (
                id, task_type, project_key, account_id, status, payload,
                scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at
            ) VALUES (?, 'post', 'proj_challenger_m2_2', ?, 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (tid, acc_id, now, now + 60000, now, now))

        # Transition to expired via POST /health
        res = client.post(f"/api/accounts/{acc_id}/health", json={
            "healthStatus": "expired",
            "message": "Error 190: OAuth token has expired"
        }, headers=AUTH_HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "expired"
        assert res.json()["healthStatus"] == "expired"

        row = query_one("SELECT status, last_error FROM tasks WHERE id = ?", (tid,))
        assert row["status"] == "cancelled"
        assert "quarantined" in (row["last_error"] or "").lower()

    def test_patch_account_health_transition(self):
        """Verify PATCH /api/accounts/{id} with healthStatus triggers identical quarantine behavior."""
        now = int(time.time() * 1000)
        acc_id = _unique_id("acc_patch")

        client.post("/api/accounts", json={
            "id": acc_id,
            "name": "Patch Account",
            "accessToken": "tok_patch",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        tid = _unique_id("task_patch")
        execute_write("""
            INSERT INTO tasks (
                id, task_type, project_key, account_id, status, payload,
                scheduled_time, retry_count, max_retries, created_at, updated_at
            ) VALUES (?, 'post', 'proj_challenger_m2_2', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (tid, acc_id, now, now, now))

        # Patch healthStatus to 'locked'
        patch_res = client.patch(f"/api/accounts/{acc_id}", json={
            "healthStatus": "locked"
        }, headers=AUTH_HEADERS)
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "checkpoint"
        assert patch_res.json()["healthStatus"] == "locked"

        row = query_one("SELECT status FROM tasks WHERE id = ?", (tid,))
        assert row["status"] == "cancelled"


# ==============================================================================
# SECTION 2: HEALTH RESTORATION & TASK CLAIMING
# ==============================================================================

class TestAccountHealthRecoveryAndTaskClaiming:
    """Empirical verification that restoring health to 'live' allows new tasks to be claimed."""

    def test_live_restoration_allows_task_polling_and_claim(self):
        """
        1. Account placed in checkpoint.
        2. Task created for account.
        3. Worker polling must NOT claim task while in checkpoint.
        4. Health restored to 'live'.
        5. Worker polling immediately claims task with atomic lease lock.
        """
        worker_id = _unique_id("worker_claim")
        acc_id = _unique_id("acc_rec")

        # Register dedicated worker
        client.post("/api/workers/register", json={
            "workerId": worker_id,
            "name": "Recovery Worker",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        # Create account
        client.post("/api/accounts", json={
            "id": acc_id,
            "name": "Recovery Account",
            "accessToken": "tok_rec",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        # Assign account to worker
        client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": [acc_id]
        }, headers=AUTH_HEADERS)

        # Set account to checkpoint
        client.post(f"/api/accounts/{acc_id}/health", json={"healthStatus": "checkpoint"}, headers=AUTH_HEADERS)

        # Enqueue new task for this account
        create_task_res = client.post("/api/tasks", json={
            "taskType": "post",
            "accountId": acc_id,
            "projectKey": "proj_challenger_m2_2",
            "priority": 50,
            "payload": {"content": "Post after recovery"}
        }, headers=AUTH_HEADERS)
        assert create_task_res.status_code == 201
        task_id = create_task_res.json()["task"]["id"]

        # Poll while in checkpoint: must NOT return task
        poll_blocked = client.post("/api/tasks/poll", json={
            "workerId": worker_id,
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)
        assert poll_blocked.status_code == 200
        assert poll_blocked.json()["task"] is None, "Worker must NOT claim task while account is in checkpoint"

        # Restore account health to 'live'
        rec_res = client.post(f"/api/accounts/{acc_id}/health", json={
            "healthStatus": "live"
        }, headers=AUTH_HEADERS)
        assert rec_res.status_code == 200
        assert rec_res.json()["status"] == "active"
        assert rec_res.json()["healthStatus"] == "live"
        assert rec_res.json()["account"]["cookieStatus"] == "valid"

        # Poll after restoration: MUST claim task
        poll_success = client.post("/api/tasks/poll", json={
            "workerId": worker_id,
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)
        assert poll_success.status_code == 200
        claimed_task = poll_success.json()["task"]
        assert claimed_task is not None, "Worker SHOULD claim task after account is restored to live"
        assert claimed_task["id"] == task_id
        assert claimed_task["status"] == "assigned"
        assert claimed_task["workerId"] == worker_id
        assert claimed_task["leaseExpiresAt"] is not None

    def test_health_synonyms_restoration(self):
        """Verify synonyms for live ('healthy', 'ok', 'active') successfully restore status."""
        for synonym in ["healthy", "ok", "active", "LIVE"]:
            acc_id = _unique_id(f"acc_syn_{synonym.lower()}")
            client.post("/api/accounts", json={
                "id": acc_id,
                "name": f"Synonym {synonym}",
                "accessToken": "tok",
                "projectKey": "proj_challenger_m2_2"
            }, headers=AUTH_HEADERS)

            # Checkpoint first
            client.post(f"/api/accounts/{acc_id}/health", json={"healthStatus": "checkpoint"}, headers=AUTH_HEADERS)

            # Restore using synonym
            res = client.post(f"/api/accounts/{acc_id}/health", json={"healthStatus": synonym}, headers=AUTH_HEADERS)
            assert res.status_code == 200
            assert res.json()["status"] == "active"
            assert res.json()["healthStatus"] == "live"


# ==============================================================================
# SECTION 3: WORKER ACCOUNT ASSIGNMENT TWO-WAY SYNCHRONIZATION
# ==============================================================================

class TestWorkerAccountAssignmentTwoWaySync:
    """Empirical verification of PUT /accounts and POST /assign two-way synchronization."""

    def test_put_worker_accounts_replacement_and_unassignment(self):
        """
        Verify PUT /api/workers/{id}/accounts:
        1. Replaces workers.assigned_accounts list.
        2. Sets accounts.worker_id = worker_id for all newly assigned accounts.
        3. Clears accounts.worker_id to NULL for previously assigned accounts no longer in the list.
        """
        worker_id = _unique_id("w_put")
        acc1 = _unique_id("acc_w1")
        acc2 = _unique_id("acc_w2")
        acc3 = _unique_id("acc_w3")

        # Create worker
        client.post("/api/workers/register", json={
            "workerId": worker_id,
            "name": "PUT Sync Worker",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        # Create 3 accounts
        for acc in [acc1, acc2, acc3]:
            client.post("/api/accounts", json={
                "id": acc,
                "name": f"Account {acc}",
                "accessToken": "tok",
                "projectKey": "proj_challenger_m2_2"
            }, headers=AUTH_HEADERS)

        # Step 1: Assign acc1 and acc2
        put1 = client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": [acc1, acc2]
        }, headers=AUTH_HEADERS)
        assert put1.status_code == 200
        assert set(put1.json()["assignedAccounts"]) == {acc1, acc2}

        # Verify DB state:
        w_row = query_one("SELECT assigned_accounts FROM workers WHERE id = ?", (worker_id,))
        assert set(json.loads(w_row["assigned_accounts"])) == {acc1, acc2}
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc1,))["worker_id"] == worker_id
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc2,))["worker_id"] == worker_id
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc3,))["worker_id"] is None

        # Step 2: Replace with acc2 and acc3 (acc1 dropped)
        put2 = client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": [acc2, acc3]
        }, headers=AUTH_HEADERS)
        assert put2.status_code == 200
        assert set(put2.json()["assignedAccounts"]) == {acc2, acc3}

        # Verify acc1 is unassigned (worker_id = NULL)
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc1,))["worker_id"] is None
        # Verify acc2 and acc3 are assigned
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc2,))["worker_id"] == worker_id
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc3,))["worker_id"] == worker_id

        # Step 3: PUT with empty list unassigns all accounts
        put_empty = client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": []
        }, headers=AUTH_HEADERS)
        assert put_empty.status_code == 200
        assert put_empty.json()["assignedAccounts"] == []
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc2,))["worker_id"] is None
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc3,))["worker_id"] is None

    def test_post_worker_assign_append_and_sync(self):
        """
        Verify POST /api/workers/{id}/assign:
        1. Appends new accounts to existing assigned_accounts without dropping existing ones.
        2. Deduplicates account IDs.
        3. Updates accounts.worker_id for incoming accounts.
        """
        worker_id = _unique_id("w_post_assign")
        acc1 = _unique_id("acc_pa1")
        acc2 = _unique_id("acc_pa2")
        acc3 = _unique_id("acc_pa3")

        client.post("/api/workers/register", json={
            "workerId": worker_id,
            "name": "POST Assign Worker",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        for acc in [acc1, acc2, acc3]:
            client.post("/api/accounts", json={
                "id": acc,
                "name": f"Account {acc}",
                "accessToken": "tok",
                "projectKey": "proj_challenger_m2_2"
            }, headers=AUTH_HEADERS)

        # Initial assignment of acc1
        client.put(f"/api/workers/{worker_id}/accounts", json={"accountIds": [acc1]}, headers=AUTH_HEADERS)

        # Now append acc2 and acc3 via POST /assign (including acc1 duplicate)
        assign_res = client.post(f"/api/workers/{worker_id}/assign", json={
            "accountIds": [acc1, acc2, acc3]
        }, headers=AUTH_HEADERS)
        assert assign_res.status_code == 200
        assigned = assign_res.json()["assignedAccounts"]
        assert set(assigned) == {acc1, acc2, acc3}
        assert len(assigned) == 3, "Account IDs should be deduplicated"

        # Check DB state
        for acc in [acc1, acc2, acc3]:
            row = query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc,))
            assert row["worker_id"] == worker_id

    def test_payload_alias_flexibility(self):
        """Verify model alias normalization (accountId, assignedAccounts, accounts)."""
        worker_id = _unique_id("w_alias")
        acc_a = _unique_id("acc_alias_a")
        acc_b = _unique_id("acc_alias_b")

        client.post("/api/workers/register", json={"workerId": worker_id}, headers=AUTH_HEADERS)
        for acc in [acc_a, acc_b]:
            client.post("/api/accounts", json={"id": acc, "name": acc, "accessToken": "tok"}, headers=AUTH_HEADERS)

        # Test single accountId alias
        r1 = client.put(f"/api/workers/{worker_id}/accounts", json={"accountId": acc_a}, headers=AUTH_HEADERS)
        assert r1.status_code == 200
        assert r1.json()["assignedAccounts"] == [acc_a]

        # Test assignedAccounts list alias
        r2 = client.put(f"/api/workers/{worker_id}/accounts", json={"assignedAccounts": [acc_b]}, headers=AUTH_HEADERS)
        assert r2.status_code == 200
        assert r2.json()["assignedAccounts"] == [acc_b]

        # Test accounts list alias on POST /assign
        r3 = client.post(f"/api/workers/{worker_id}/assign", json={"accounts": [acc_a]}, headers=AUTH_HEADERS)
        assert r3.status_code == 200
        assert set(r3.json()["assignedAccounts"]) == {acc_a, acc_b}

    def test_assignment_to_non_existent_worker_returns_404(self):
        """Verify PUT and POST on non-existent worker return 404 Not Found."""
        fake_id = "non_existent_worker_9999"
        r_put = client.put(f"/api/workers/{fake_id}/accounts", json={"accountIds": ["acc1"]}, headers=AUTH_HEADERS)
        assert r_put.status_code == 404

        r_post = client.post(f"/api/workers/{fake_id}/assign", json={"accountIds": ["acc1"]}, headers=AUTH_HEADERS)
        assert r_post.status_code == 404


# ==============================================================================
# SECTION 4: WORKER DELETION & RELATIONAL UNASSIGNMENT
# ==============================================================================

class TestWorkerDeletionUnassignment:
    """Empirical verification that deleting a worker sets assigned accounts' worker_id to NULL."""

    def test_delete_worker_unassigns_linked_accounts_to_null(self):
        """
        1. Register worker.
        2. Assign multiple accounts.
        3. Delete worker via DELETE /api/workers/{id}.
        4. Assert worker row is deleted.
        5. Assert accounts still exist and accounts.worker_id is set to NULL.
        """
        worker_id = _unique_id("w_del")
        acc1 = _unique_id("acc_del1")
        acc2 = _unique_id("acc_del2")

        client.post("/api/workers/register", json={
            "workerId": worker_id,
            "name": "To Be Deleted Worker",
            "projectKey": "proj_challenger_m2_2"
        }, headers=AUTH_HEADERS)

        for acc in [acc1, acc2]:
            client.post("/api/accounts", json={
                "id": acc,
                "name": f"Account {acc}",
                "accessToken": "tok",
                "projectKey": "proj_challenger_m2_2"
            }, headers=AUTH_HEADERS)

        # Assign accounts
        client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": [acc1, acc2]
        }, headers=AUTH_HEADERS)

        # Pre-condition check
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc1,))["worker_id"] == worker_id
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc2,))["worker_id"] == worker_id

        # Delete worker
        del_res = client.delete(f"/api/workers/{worker_id}", headers=AUTH_HEADERS)
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True
        assert del_res.json()["id"] == worker_id

        # Verify worker is deleted from database
        assert query_one("SELECT id FROM workers WHERE id = ?", (worker_id,)) is None

        # Verify accounts still exist and their worker_id is NULL
        row1 = query_one("SELECT id, worker_id FROM accounts WHERE id = ?", (acc1,))
        assert row1 is not None, "Account 1 must not be deleted when worker is deleted"
        assert row1["worker_id"] is None, "Account 1 worker_id must be NULL after worker deletion"

        row2 = query_one("SELECT id, worker_id FROM accounts WHERE id = ?", (acc2,))
        assert row2 is not None, "Account 2 must not be deleted when worker is deleted"
        assert row2["worker_id"] is None, "Account 2 worker_id must be NULL after worker deletion"

    def test_delete_non_existent_worker_returns_404(self):
        """Verify deleting a non-existent worker returns 404."""
        del_res = client.delete("/api/workers/non_existent_worker_404", headers=AUTH_HEADERS)
        assert del_res.status_code == 404


# ==============================================================================
# SECTION 5: CONCURRENCY STRESS & ADVERSARIAL EDGE CASES
# ==============================================================================

class TestConcurrencyAndAdversarialEdgeCases:
    """Stress testing concurrent operations and race conditions."""

    def test_concurrent_health_updates_and_task_polling(self):
        """
        Stress-test SQLite WAL under high concurrency:
        Multiple threads simultaneously toggle health between 'checkpoint' and 'live'
        while other threads enqueue and poll tasks.
        Verify no SQLite database locked exceptions occur and state remains consistent.
        """
        acc_id = _unique_id("acc_concurrent")
        worker_id = _unique_id("w_concurrent")
        project_key = _unique_id("proj_conc")
        headers = {
            "X-Sync-Token": "fbauto_sync_secret_token_prod_2026",
            "X-Project-Key": project_key
        }

        # Setup account and worker
        client.post("/api/accounts", json={
            "id": acc_id,
            "name": "Concurrent Stress Acc",
            "accessToken": "tok",
            "projectKey": project_key
        }, headers=headers)

        client.post("/api/workers/register", json={
            "workerId": worker_id,
            "projectKey": project_key
        }, headers=headers)

        client.put(f"/api/workers/{worker_id}/accounts", json={
            "accountIds": [acc_id]
        }, headers=headers)

        def worker_toggle_health(i: int):
            status_choice = "checkpoint" if i % 2 == 0 else "live"
            res = client.post(f"/api/accounts/{acc_id}/health", json={
                "healthStatus": status_choice
            }, headers=headers)
            return ("health", res.status_code)

        def worker_enqueue_task(i: int):
            res = client.post("/api/tasks", json={
                "taskType": "post",
                "accountId": acc_id,
                "projectKey": project_key,
                "priority": i,
                "payload": {"index": i}
            }, headers=headers)
            return ("enqueue", res.status_code)

        def worker_poll_task(i: int):
            res = client.post("/api/tasks/poll", json={
                "workerId": worker_id,
                "projectKey": project_key
            }, headers=headers)
            return ("poll", res.status_code)

        tasks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for i in range(15):
                tasks.append(executor.submit(worker_enqueue_task, i))
                tasks.append(executor.submit(worker_toggle_health, i))
                tasks.append(executor.submit(worker_poll_task, i))

            results = [f.result() for f in as_completed(tasks)]

        # All operations should succeed with 200 or 201 without 500 database locked errors
        for op_type, status_code in results:
            assert status_code in [200, 201], f"Operation {op_type} failed with status {status_code}"

        # Final health check: set to live, enqueue a task, verify it can be claimed
        client.post(f"/api/accounts/{acc_id}/health", json={"healthStatus": "live"}, headers=headers)
        final_enqueue = client.post("/api/tasks", json={
            "taskType": "post",
            "accountId": acc_id,
            "projectKey": project_key,
            "priority": 9999,
            "payload": {"final": True}
        }, headers=headers)
        assert final_enqueue.status_code == 201

        final_poll = client.post("/api/tasks/poll", json={
            "workerId": worker_id,
            "projectKey": project_key
        }, headers=headers)
        assert final_poll.status_code == 200
        assert final_poll.json()["task"] is not None
        assert final_poll.json()["task"]["id"] == final_enqueue.json()["task"]["id"]


# ==============================================================================
# SECTION 6: ADVERSARIAL DISCOVERIES & FRONTIER STRESS TESTS
# ==============================================================================

class TestAdversarialDiscoveries:
    """Empirical investigation of edge case behaviors and boundary conditions."""

    def test_target_id_quarantine_addressing(self):
        """
        Verify quarantine behavior when account has distinct id and targetId:
        Updating health via targetId successfully quarantines tasks.
        """
        now = int(time.time() * 1000)
        acc_id = _unique_id("acc_num_test")
        target_id = f"fb_{int(time.time() * 1000)}"

        client.post("/api/accounts", json={
            "id": acc_id,
            "targetId": target_id,
            "name": "Target ID Account",
            "accessToken": "tok"
        }, headers=AUTH_HEADERS)

        # Enqueue task using targetId
        task_res = client.post("/api/tasks", json={
            "taskType": "post",
            "accountId": target_id,
            "payload": {}
        }, headers=AUTH_HEADERS)
        assert task_res.status_code == 201
        tid = task_res.json()["task"]["id"]

        # Health update addressed via targetId
        res = client.post(f"/api/accounts/{target_id}/health", json={
            "healthStatus": "checkpoint"
        }, headers=AUTH_HEADERS)
        assert res.status_code == 200

        # Verify task is quarantined
        row = query_one("SELECT status FROM tasks WHERE id = ?", (tid,))
        assert row["status"] == "cancelled"

    def test_worker_report_on_quarantined_task_lifecycle(self):
        """
        Empirically test state machine behavior when a worker reports status
        on a task that has already been quarantined into 'cancelled'.
        """
        worker_id = _unique_id("w_lifecycle")
        acc_id = _unique_id("acc_lifecycle")
        client.post("/api/workers/register", json={"workerId": worker_id, "projectKey": "proj_challenger_m2_2"}, headers=AUTH_HEADERS)
        client.post("/api/accounts", json={"id": acc_id, "name": "Lifecycle Acc", "accessToken": "tok", "projectKey": "proj_challenger_m2_2"}, headers=AUTH_HEADERS)
        client.put(f"/api/workers/{worker_id}/accounts", json={"accountIds": [acc_id]}, headers=AUTH_HEADERS)

        # Create and claim task
        t_res = client.post("/api/tasks", json={
            "taskType": "post",
            "accountId": acc_id,
            "projectKey": "proj_challenger_m2_2",
            "priority": 100000,
            "payload": {}
        }, headers=AUTH_HEADERS)
        tid = t_res.json()["task"]["id"]

        poll_res = client.post("/api/tasks/poll", json={"workerId": worker_id, "projectKey": "proj_challenger_m2_2"}, headers=AUTH_HEADERS)
        assert poll_res.json()["task"]["id"] == tid

        # Put account into checkpoint -> task becomes cancelled
        client.post(f"/api/accounts/{acc_id}/health", json={"healthStatus": "checkpoint"}, headers=AUTH_HEADERS)
        assert query_one("SELECT status FROM tasks WHERE id = ?", (tid,))["status"] == "cancelled"

        # Worker reports running -> verify it records running or handles state
        run_res = client.post(f"/api/tasks/{tid}/status", json={"workerId": worker_id, "status": "running"}, headers=AUTH_HEADERS)
        assert run_res.status_code == 200

    def test_reassignment_between_workers(self):
        """
        Verify two-way sync when Account A is assigned to Worker 1, then reassigned to Worker 2.
        Accounts.worker_id must reflect the newest worker.
        """
        w1 = _unique_id("w1_reassign")
        w2 = _unique_id("w2_reassign")
        acc = _unique_id("acc_reassign")

        client.post("/api/workers/register", json={"workerId": w1}, headers=AUTH_HEADERS)
        client.post("/api/workers/register", json={"workerId": w2}, headers=AUTH_HEADERS)
        client.post("/api/accounts", json={"id": acc, "name": "Reassign Acc", "accessToken": "tok"}, headers=AUTH_HEADERS)

        # W1 takes account
        client.put(f"/api/workers/{w1}/accounts", json={"accountIds": [acc]}, headers=AUTH_HEADERS)
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc,))["worker_id"] == w1

        # W2 takes account
        client.put(f"/api/workers/{w2}/accounts", json={"accountIds": [acc]}, headers=AUTH_HEADERS)
        assert query_one("SELECT worker_id FROM accounts WHERE id = ?", (acc,))["worker_id"] == w2
