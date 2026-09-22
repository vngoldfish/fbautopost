"""
test_challenger_m2_1_queue.py
Empirical Challenger Test Suite for Milestone 2:
Distributed Task Queue Engine & Zombie Task Lease Watchdog.

Author: challenger_m2_1 (Empirical Challenger)
Covers:
1. Zombie Task Lease Watchdog:
   - Expired running and assigned tasks automatically reclaimed to pending when retry_count < max_retries.
   - retry_count incremented, worker_id cleared, lease_expires_at cleared.
   - Tasks with retry_count >= max_retries transition permanently to status 'failed' with error.
   - Edge cases: boundary timing (< vs ==), max_retries=0, null max_retries, terminal status preservation.
   - Background scheduler thread execution.
   - Multi-worker crash & full lifecycle retry exhaustion.
2. Task Queue Mechanics & Lease Locking:
   - Task claims grant 60s lease duration (now_ms + 60,000ms).
   - Anti-collision concurrency: single task with 20 competing workers.
   - Anti-collision concurrency: multi-task with 20-50 competing workers.
   - Heartbeat lease extension prevents premature watchdog reclamation.
   - Account quarantine / checkpoint exclusion and account affinity matching.
"""

import os
import sys
import time
import json
import threading
from typing import List, Dict, Any, Optional
import pytest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app.core.config import settings
from app.db.session import execute_write, query_one, query_all
from app.services.scheduler_service import reclaim_zombie_tasks, start_scheduler, stop_scheduler

client = TestClient(app)
SYNC_TOKEN = settings.SYNC_TOKEN or "fbauto_sync_secret_token_prod_2026"


def make_headers(worker_id: str, project_key: str, ip: str = "10.99.1.1") -> Dict[str, str]:
    return {
        "X-Sync-Token": SYNC_TOKEN,
        "X-Project-Key": project_key,
        "X-Worker-Id": worker_id,
        "X-Forwarded-For": ip
    }


class TestZombieTaskLeaseWatchdog:
    """Empirical verification of Zombie Task Lease Watchdog mechanics."""

    def test_reclaim_expired_running_task_increments_retry_and_resets_pending(self):
        """Expired running task is reclaimed to pending, retry_count incremented, lease cleared."""
        now = int(time.time() * 1000)
        proj = f"proj_z_run_{now}"
        task_id = f"task_z_run_{now}"
        worker_id = f"w_z_run_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (task_id, proj, worker_id, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaimed = reclaim_zombie_tasks(now)
        assert reclaimed >= 1

        t = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t["status"] == "pending"
        assert t["retry_count"] == 1
        assert t["worker_id"] is None
        assert t["lease_expires_at"] is None

        # Clean up
        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_reclaim_expired_assigned_task_increments_retry_and_resets_pending(self):
        """Expired assigned task is reclaimed to pending, retry_count incremented, lease cleared."""
        now = int(time.time() * 1000)
        proj = f"proj_z_asg_{now}"
        task_id = f"task_z_asg_{now}"
        worker_id = f"w_z_asg_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'assigned', '{}', ?, 1, 3, ?, ?, ?)
        """, (task_id, proj, worker_id, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaimed = reclaim_zombie_tasks(now)
        assert reclaimed >= 1

        t = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t["status"] == "pending"
        assert t["retry_count"] == 2
        assert t["worker_id"] is None
        assert t["lease_expires_at"] is None

        # Clean up
        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_unexpired_task_not_reclaimed(self):
        """Active task with future lease_expires_at is untouched by watchdog."""
        now = int(time.time() * 1000)
        proj = f"proj_z_act_{now}"
        task_id = f"task_z_act_{now}"
        worker_id = f"w_z_act_{now}"
        future_lease = now + 45000

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (task_id, proj, worker_id, now - 5000, future_lease, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        t = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t["status"] == "running"
        assert t["worker_id"] == worker_id
        assert t["lease_expires_at"] == future_lease
        assert t["retry_count"] == 0

        # Clean up
        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_terminal_status_tasks_not_reclaimed(self):
        """Tasks in completed or failed status are not modified even if lease_expires_at is past."""
        now = int(time.time() * 1000)
        proj = f"proj_z_term_{now}"
        t_comp = f"t_comp_{now}"
        t_fail = f"t_fail_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, 'completed', '{}', ?, 0, 3, ?, ?, ?)
        """, (t_comp, proj, now - 5000, now - 1000, now - 5000, now - 5000))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, 'failed', '{}', ?, 3, 3, ?, ?, ?)
        """, (t_fail, proj, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        comp = query_one("SELECT * FROM tasks WHERE id = ?", (t_comp,))
        fail = query_one("SELECT * FROM tasks WHERE id = ?", (t_fail,))
        assert comp["status"] == "completed"
        assert fail["status"] == "failed"

        # Clean up
        execute_write("DELETE FROM tasks WHERE id IN (?, ?)", (t_comp, t_fail))

    def test_max_retries_exceeded_transitions_permanently_to_failed(self):
        """Tasks with retry_count >= max_retries transition permanently to status 'failed'."""
        now = int(time.time() * 1000)
        proj = f"proj_z_exhaust_{now}"
        task_id = f"task_z_exhaust_{now}"
        worker_id = f"w_z_exhaust_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'running', '{}', ?, 3, 3, ?, ?, ?)
        """, (task_id, proj, worker_id, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        t = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t["status"] == "failed"
        assert t["retry_count"] == 3
        assert t["lease_expires_at"] is None
        assert "Lease expired and max retries exceeded" in t["last_error"]

        # Re-running watchdog does not alter or re-process the failed task
        reclaim_zombie_tasks(now + 10000)
        t_again = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t_again["status"] == "failed"

        # Clean up
        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_max_retries_zero_immediately_fails(self):
        """Tasks configured with max_retries=0 fail immediately on first lease expiration."""
        now = int(time.time() * 1000)
        proj = f"proj_z_zero_{now}"
        task_id = f"task_z_zero_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, 'running', '{}', ?, 0, 0, ?, ?, ?)
        """, (task_id, proj, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        t = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t["status"] == "failed"
        assert t["retry_count"] == 0
        assert "Lease expired and max retries exceeded" in t["last_error"]

        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_null_max_retries_defaults_to_three(self):
        """Tasks with NULL max_retries default to 3 retries before failing."""
        now = int(time.time() * 1000)
        proj = f"proj_z_null_{now}"
        task_id = f"task_z_null_{now}"

        # retry_count=2, max_retries=NULL -> should be reclaimed to pending (retry_count=3)
        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', ?, 'running', '{}', ?, 2, NULL, ?, ?, ?)
        """, (task_id, proj, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)
        t1 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t1["status"] == "pending"
        assert t1["retry_count"] == 3

        # Next expiration with retry_count=3 -> should fail
        execute_write("UPDATE tasks SET status = 'running', lease_expires_at = ? WHERE id = ?", (now + 5000, task_id))
        reclaim_zombie_tasks(now + 10000)
        t2 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t2["status"] == "failed"
        assert "Lease expired and max retries exceeded" in t2["last_error"]

        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))

    def test_worker_current_task_cleared_on_reclaim(self):
        """Worker's current_task_id is cleared when its zombie task is reclaimed."""
        now = int(time.time() * 1000)
        task_id = f"task_w_clear_{now}"
        worker_id = f"w_victim_{now}"

        execute_write("""
            INSERT INTO workers (id, name, project_key, status, last_heartbeat, current_task_id, created_at, updated_at)
            VALUES (?, 'VictimNode', 'all', 'busy', ?, ?, ?, ?)
        """, (worker_id, now, task_id, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'all', ?, 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (task_id, worker_id, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        w = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
        assert w["current_task_id"] is None

        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))
        execute_write("DELETE FROM workers WHERE id = ?", (worker_id,))

    def test_worker_current_task_not_cleared_if_worker_switched_task(self):
        """Watchdog does not clear worker's current_task_id if worker has moved on to a different task."""
        now = int(time.time() * 1000)
        task_stale = f"task_stale_{now}"
        task_active = f"task_active_{now}"
        worker_id = f"w_switch_{now}"

        execute_write("""
            INSERT INTO workers (id, name, project_key, status, last_heartbeat, current_task_id, created_at, updated_at)
            VALUES (?, 'SwitchedNode', 'all', 'busy', ?, ?, ?, ?)
        """, (worker_id, now, task_active, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'all', ?, 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (task_stale, worker_id, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        w = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
        assert w["current_task_id"] == task_active

        execute_write("DELETE FROM tasks WHERE id = ?", (task_stale,))
        execute_write("DELETE FROM workers WHERE id = ?", (worker_id,))

    def test_activity_logs_emitted_on_reclaim_and_failure(self):
        """TASK_LEASE_RECLAIMED and TASK_LEASE_EXPIRED_FAILED audit logs are persisted."""
        now = int(time.time() * 1000)
        t_rec = f"t_log_rec_{now}"
        t_fail = f"t_log_fail_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'p_log', 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (t_rec, now - 5000, now - 1000, now - 5000, now - 5000))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'p_log', 'running', '{}', ?, 3, 3, ?, ?, ?)
        """, (t_fail, now - 5000, now - 1000, now - 5000, now - 5000))

        reclaim_zombie_tasks(now)

        log_rec = query_one("SELECT * FROM logs WHERE action = 'TASK_LEASE_RECLAIMED' AND entity_id = ?", (t_rec,))
        assert log_rec is not None
        assert log_rec["entity_type"] == "task"

        log_fail = query_one("SELECT * FROM logs WHERE action = 'TASK_LEASE_EXPIRED_FAILED' AND entity_id = ?", (t_fail,))
        assert log_fail is not None
        assert log_fail["entity_type"] == "task"

        execute_write("DELETE FROM tasks WHERE id IN (?, ?)", (t_rec, t_fail))
        execute_write("DELETE FROM logs WHERE entity_id IN (?, ?)", (t_rec, t_fail))

    def test_exact_millisecond_lease_boundary(self):
        """Strict inequality: lease_expires_at < now is reclaimed, == now or > now is active."""
        now = int(time.time() * 1000)
        t_past = f"t_b_past_{now}"
        t_exact = f"t_b_exact_{now}"
        t_future = f"t_b_fut_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'b_test', 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (t_past, now, now - 1, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'b_test', 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (t_exact, now, now, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'b_test', 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (t_future, now, now + 1000, now, now))

        reclaim_zombie_tasks(now)

        r_past = query_one("SELECT status FROM tasks WHERE id = ?", (t_past,))
        r_exact = query_one("SELECT status FROM tasks WHERE id = ?", (t_exact,))
        r_future = query_one("SELECT status FROM tasks WHERE id = ?", (t_future,))

        assert r_past["status"] == "pending"
        assert r_exact["status"] == "running"
        assert r_future["status"] == "running"

        execute_write("DELETE FROM tasks WHERE id IN (?, ?, ?)", (t_past, t_exact, t_future))

    def test_background_scheduler_thread_reclaims_automatically(self):
        """Active background scheduler thread automatically scans and reclaims expired tasks."""
        now = int(time.time() * 1000)
        task_id = f"task_bg_loop_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, lease_expires_at, created_at, updated_at)
            VALUES (?, 'post', 'bg_test', 'running', '{}', ?, 0, 3, ?, ?, ?)
        """, (task_id, now - 5000, now - 1000, now - 5000, now - 5000))

        start_scheduler(interval_sec=1)
        reclaimed = False
        for _ in range(6):
            time.sleep(0.5)
            row = query_one("SELECT status, retry_count FROM tasks WHERE id = ?", (task_id,))
            if row and row["status"] == "pending" and row["retry_count"] == 1:
                reclaimed = True
                break

        stop_scheduler()
        execute_write("DELETE FROM tasks WHERE id = ?", (task_id,))
        assert reclaimed, "Background scheduler failed to reclaim expired task"

    def test_full_lifecycle_multi_worker_retry_exhaustion(self):
        """End-to-end multi-worker crash cycle through max retries to terminal failed status."""
        now = int(time.time() * 1000)
        proj = f"proj_full_life_{now}"
        task_id = f"task_full_life_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, now, now, now))

        # Cycle 1: Worker 1 claims, crashes
        res1 = client.post("/api/tasks/poll", json={"workerId": "w1", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w1", proj, "10.1.1.1"))
        assert res1.json()["task"]["id"] == task_id
        assert res1.json()["task"]["retryCount"] == 0

        t1 = now + 61000
        reclaim_zombie_tasks(t1)
        db1 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db1["status"] == "pending"
        assert db1["retry_count"] == 1

        # Cycle 2: Worker 2 claims, crashes
        res2 = client.post("/api/tasks/poll", json={"workerId": "w2", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w2", proj, "10.1.1.2"))
        assert res2.json()["task"]["id"] == task_id
        assert res2.json()["task"]["retryCount"] == 1

        t2 = t1 + 61000
        reclaim_zombie_tasks(t2)
        db2 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db2["status"] == "pending"
        assert db2["retry_count"] == 2

        # Cycle 3: Worker 3 claims, reports running, then crashes
        res3 = client.post("/api/tasks/poll", json={"workerId": "w3", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w3", proj, "10.1.1.3"))
        assert res3.json()["task"]["id"] == task_id
        assert res3.json()["task"]["retryCount"] == 2
        client.post(f"/api/tasks/{task_id}/status", json={"workerId": "w3", "status": "running"}, headers=make_headers("w3", proj, "10.1.1.3"))

        t3 = t2 + 61000
        reclaim_zombie_tasks(t3)
        db3 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db3["status"] == "pending"
        assert db3["retry_count"] == 3

        # Cycle 4: Worker 4 claims, crashes -> Max retries reached (3 >= 3)
        res4 = client.post("/api/tasks/poll", json={"workerId": "w4", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w4", proj, "10.1.1.4"))
        assert res4.json()["task"]["id"] == task_id
        assert res4.json()["task"]["retryCount"] == 3

        t4 = t3 + 61000
        reclaim_zombie_tasks(t4)
        db4 = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db4["status"] == "failed"
        assert db4["retry_count"] == 3
        assert db4["lease_expires_at"] is None
        assert "max retries exceeded" in db4["last_error"]

        # Final verification: subsequent poll by Worker 5 returns None
        res5 = client.post("/api/tasks/poll", json={"workerId": "w5", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w5", proj, "10.1.1.5"))
        assert res5.json()["task"] is None

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id IN ('w1', 'w2', 'w3', 'w4', 'w5')")


class TestTaskQueueLeaseAndConcurrency:
    """Empirical verification of lease duration, anti-collision, and queue mechanics."""

    def test_poll_task_grants_60s_lease_duration(self):
        """Claiming a task assigns an exact 60,000ms lease duration."""
        now = int(time.time() * 1000)
        proj = f"proj_lease_{now}"
        task_id = f"task_lease_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, now, now, now))

        res = client.post(
            "/api/tasks/poll",
            json={"workerId": "w_lease_test", "projectKey": proj, "supportedTypes": ["post"]},
            headers=make_headers("w_lease_test", proj, "10.2.1.1")
        )
        assert res.status_code == 200
        task = res.json()["task"]
        assert task is not None
        assert task["id"] == task_id
        assert task["status"] == "assigned"
        assert task["workerId"] == "w_lease_test"

        lease_span = task["leaseExpiresAt"] - task["claimedAt"]
        assert lease_span == 60000, f"Expected 60000ms lease, got {lease_span}ms"

        db_task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db_task["status"] == "assigned"
        assert db_task["worker_id"] == "w_lease_test"
        assert db_task["lease_expires_at"] is not None

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id = 'w_lease_test'")

    def test_poll_task_empty_queue_returns_null(self):
        """When no pending tasks exist, poll endpoint returns { task: None } with 200."""
        proj = f"proj_empty_{int(time.time() * 1000)}"
        res = client.post(
            "/api/tasks/poll",
            json={"workerId": "w_empty", "projectKey": proj, "supportedTypes": ["post"]},
            headers=make_headers("w_empty", proj, "10.2.1.2")
        )
        assert res.status_code == 200
        assert res.json()["task"] is None
        execute_write("DELETE FROM workers WHERE id = 'w_empty'")

    def test_poll_task_future_scheduled_task_not_claimed(self):
        """Tasks scheduled for the future (scheduled_time > now) are not claimed."""
        now = int(time.time() * 1000)
        proj = f"proj_future_{now}"
        task_id = f"task_future_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, now + 300000, now, now))

        res = client.post(
            "/api/tasks/poll",
            json={"workerId": "w_fut", "projectKey": proj, "supportedTypes": ["post"]},
            headers=make_headers("w_fut", proj, "10.2.1.3")
        )
        assert res.json()["task"] is None

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id = 'w_fut'")

    def test_poll_task_priority_ordering(self):
        """Tasks with higher priority are claimed before lower priority tasks."""
        now = int(time.time() * 1000)
        proj = f"proj_prio_{now}"
        t_low = f"t_prio_0_{now}"
        t_med = f"t_prio_5_{now}"
        t_high = f"t_prio_10_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 0, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (t_low, proj, now, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 10, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (t_high, proj, now, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, priority, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 5, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (t_med, proj, now, now, now))

        # Claim 1: priority 10
        r1 = client.post("/api/tasks/poll", json={"workerId": "w_p1", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w_p1", proj, "10.2.1.4"))
        assert r1.json()["task"]["id"] == t_high

        # Claim 2: priority 5
        r2 = client.post("/api/tasks/poll", json={"workerId": "w_p2", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w_p2", proj, "10.2.1.5"))
        assert r2.json()["task"]["id"] == t_med

        # Claim 3: priority 0
        r3 = client.post("/api/tasks/poll", json={"workerId": "w_p3", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w_p3", proj, "10.2.1.6"))
        assert r3.json()["task"]["id"] == t_low

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id IN ('w_p1', 'w_p2', 'w_p3')")

    def test_heartbeat_lease_extension_prevents_watchdog_reclaim(self):
        """Worker heartbeat renewal extends lease and protects against watchdog reclamation."""
        now = int(time.time() * 1000)
        proj = f"proj_hb_ext_{now}"
        task_id = f"task_hb_ext_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, now, now, now))

        res = client.post("/api/tasks/poll", json={"workerId": "w_hb", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w_hb", proj, "10.2.1.7"))
        initial_lease = res.json()["task"]["leaseExpiresAt"]

        # Extend lease by 120s
        hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 120}, headers=make_headers("w_hb", proj, "10.2.1.7"))
        assert hb_res.status_code == 200
        new_lease = hb_res.json()["leaseExpiresAt"]
        assert new_lease > initial_lease

        # Watchdog runs at initial_lease + 10s: task must remain assigned
        reclaim_zombie_tasks(initial_lease + 10000)
        t_active = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t_active["status"] == "assigned"

        # Watchdog runs at new_lease + 10s: task is reclaimed
        reclaim_zombie_tasks(new_lease + 10000)
        t_reclaimed = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert t_reclaimed["status"] == "pending"

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id = 'w_hb'")

    def test_checkpoint_account_task_excluded_from_poll(self):
        """Tasks whose target account is in checkpoint, expired, or logged_out are not claimed."""
        now = int(time.time() * 1000)
        proj = f"proj_chk_poll_{now}"
        acc_id = f"acc_chk_poll_{now}"
        task_id = f"task_chk_poll_{now}"

        execute_write("""
            INSERT INTO accounts (id, name, target_id, project_key, status, health_status, created_at, updated_at)
            VALUES (?, 'Checkpoint Acc', ?, ?, 'checkpoint', 'checkpoint', ?, ?)
        """, (acc_id, acc_id, proj, now, now))

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, account_id, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, acc_id, now, now, now))

        res = client.post("/api/tasks/poll", json={"workerId": "w_chk", "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers("w_chk", proj, "10.2.1.8"))
        assert res.json()["task"] is None

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM accounts WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id = 'w_chk'")

    def test_account_affinity_enforcement(self):
        """Worker with assigned accounts only claims tasks matching its assigned accounts."""
        now = int(time.time() * 1000)
        proj = f"proj_aff_test_{now}"
        acc_1 = f"acc_aff_1_{now}"
        acc_2 = f"acc_aff_2_{now}"
        w_1 = f"w_aff_1_{now}"
        w_2 = f"w_aff_2_{now}"
        task_1 = f"task_aff_1_{now}"

        execute_write("INSERT INTO workers (id, name, project_key, status, last_heartbeat, assigned_accounts, created_at, updated_at) VALUES (?, 'W1', ?, 'online', ?, ?, ?, ?)", (w_1, proj, now, json.dumps([acc_1]), now, now))
        execute_write("INSERT INTO workers (id, name, project_key, status, last_heartbeat, assigned_accounts, created_at, updated_at) VALUES (?, 'W2', ?, 'online', ?, ?, ?, ?)", (w_2, proj, now, json.dumps([acc_2]), now, now))

        execute_write("INSERT INTO accounts (id, name, target_id, project_key, status, worker_id, created_at, updated_at) VALUES (?, 'A1', ?, ?, 'active', ?, ?, ?)", (acc_1, acc_1, proj, w_1, now, now))
        execute_write("INSERT INTO accounts (id, name, target_id, project_key, status, worker_id, created_at, updated_at) VALUES (?, 'A2', ?, ?, 'active', ?, ?, ?)", (acc_2, acc_2, proj, w_2, now, now))

        execute_write("INSERT INTO tasks (id, task_type, project_key, account_id, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at) VALUES (?, 'post', ?, ?, 'pending', '{}', ?, 0, 3, ?, ?)", (task_1, proj, acc_1, now, now, now))

        # Worker 2 should get None (does not hold account 1)
        r2 = client.post("/api/tasks/poll", json={"workerId": w_2, "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers(w_2, proj, "10.2.1.9"))
        assert r2.json()["task"] is None

        # Worker 1 should get task_1
        r1 = client.post("/api/tasks/poll", json={"workerId": w_1, "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers(w_1, proj, "10.2.1.10"))
        assert r1.json()["task"] is not None
        assert r1.json()["task"]["id"] == task_1

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM accounts WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE project_key = ?", (proj,))

    def test_targeted_worker_claim_enforcement(self):
        """Task created with a specific worker_id is only claimed by that worker."""
        now = int(time.time() * 1000)
        proj = f"proj_target_w_{now}"
        task_id = f"task_targeted_{now}"
        target_w = f"w_target_{now}"
        other_w = f"w_other_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, worker_id, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, proj, target_w, now, now, now))

        # Other worker cannot claim
        r_other = client.post("/api/tasks/poll", json={"workerId": other_w, "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers(other_w, proj, "10.2.1.11"))
        assert r_other.json()["task"] is None

        # Target worker claims
        r_target = client.post("/api/tasks/poll", json={"workerId": target_w, "projectKey": proj, "supportedTypes": ["post"]}, headers=make_headers(target_w, proj, "10.2.1.12"))
        assert r_target.json()["task"] is not None
        assert r_target.json()["task"]["id"] == task_id

        execute_write("DELETE FROM tasks WHERE project_key = ?", (proj,))
        execute_write("DELETE FROM workers WHERE id IN (?, ?)", (target_w, other_w))

    def test_single_task_20_workers_concurrency_anti_collision(self):
        """20 concurrent workers simultaneously polling for 1 task: exactly 1 wins, 19 get None."""
        now = int(time.time() * 1000)
        test_proj = f"proj_race_single_{now}"
        task_id = f"test_single_collision_{now}"

        execute_write("""
            INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
            VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
        """, (task_id, test_proj, now, now, now))

        num_workers = 20
        barrier = threading.Barrier(num_workers)
        results = [None] * num_workers
        errors = []

        def worker_poll(idx):
            worker_id = f"w_race_s_{idx}_{now}"
            headers = make_headers(worker_id, test_proj, f"10.60.1.{idx}")
            payload = {"workerId": worker_id, "projectKey": test_proj, "supportedTypes": ["post"]}
            try:
                barrier.wait(timeout=5)
                res = client.post("/api/tasks/poll", json=payload, headers=headers)
                results[idx] = (worker_id, res.status_code, res.json())
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_poll, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency errors encountered: {errors}"
        claimed = [r for r in results if r and r[1] == 200 and r[2].get("task") is not None]
        empty = [r for r in results if r and r[1] == 200 and r[2].get("task") is None]

        assert len(claimed) == 1, f"Expected exactly 1 claim, got {len(claimed)}"
        assert len(empty) == num_workers - 1
        assert claimed[0][2]["task"]["id"] == task_id

        db_task = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert db_task["status"] == "assigned"
        assert db_task["worker_id"] == claimed[0][0]

        execute_write("DELETE FROM tasks WHERE project_key = ?", (test_proj,))
        execute_write("DELETE FROM workers WHERE id LIKE 'w_race_s_%'")

    def test_multi_task_20_workers_concurrency_anti_collision(self):
        """20 concurrent workers polling for 5 tasks: exactly 5 win, 15 get None, 5 distinct IDs."""
        now = int(time.time() * 1000)
        test_proj = f"proj_race_multi_{now}"
        num_tasks = 5
        num_workers = 20

        task_ids = [f"t_multi_{i}_{now}" for i in range(num_tasks)]
        for tid in task_ids:
            execute_write("""
                INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
                VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
            """, (tid, test_proj, now, now, now))

        barrier = threading.Barrier(num_workers)
        results = [None] * num_workers
        errors = []

        def worker_poll(idx):
            worker_id = f"w_race_m_{idx}_{now}"
            headers = make_headers(worker_id, test_proj, f"10.70.1.{idx}")
            payload = {"workerId": worker_id, "projectKey": test_proj, "supportedTypes": ["post"]}
            try:
                barrier.wait(timeout=5)
                res = client.post("/api/tasks/poll", json=payload, headers=headers)
                results[idx] = (worker_id, res.status_code, res.json())
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_poll, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency errors: {errors}"
        claimed = [r for r in results if r and r[1] == 200 and r[2].get("task") is not None]
        empty = [r for r in results if r and r[1] == 200 and r[2].get("task") is None]

        assert len(claimed) == num_tasks, f"Expected {num_tasks} claims, got {len(claimed)}"
        assert len(empty) == num_workers - num_tasks

        claimed_ids = [r[2]["task"]["id"] for r in claimed]
        assert len(set(claimed_ids)) == num_tasks, f"Duplicate task claims detected: {claimed_ids}"

        execute_write("DELETE FROM tasks WHERE project_key = ?", (test_proj,))
        execute_write("DELETE FROM workers WHERE id LIKE 'w_race_m_%'")

    def test_high_contention_50_workers_anti_collision(self):
        """50 concurrent workers competing for 10 tasks under extreme load: zero double claims."""
        now = int(time.time() * 1000)
        test_proj = f"proj_race_heavy_{now}"
        num_tasks = 10
        num_workers = 50

        task_ids = [f"t_heavy_{i}_{now}" for i in range(num_tasks)]
        for tid in task_ids:
            execute_write("""
                INSERT INTO tasks (id, task_type, project_key, status, payload, scheduled_time, retry_count, max_retries, created_at, updated_at)
                VALUES (?, 'post', ?, 'pending', '{}', ?, 0, 3, ?, ?)
            """, (tid, test_proj, now, now, now))

        barrier = threading.Barrier(num_workers)
        results = [None] * num_workers
        errors = []

        def worker_poll(idx):
            worker_id = f"w_race_h_{idx}_{now}"
            headers = make_headers(worker_id, test_proj, f"10.80.1.{idx}")
            payload = {"workerId": worker_id, "projectKey": test_proj, "supportedTypes": ["post"]}
            try:
                barrier.wait(timeout=10)
                res = client.post("/api/tasks/poll", json=payload, headers=headers)
                results[idx] = (worker_id, res.status_code, res.json())
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_poll, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrency errors: {errors}"
        claimed = [r for r in results if r and r[1] == 200 and r[2].get("task") is not None]
        empty = [r for r in results if r and r[1] == 200 and r[2].get("task") is None]

        assert len(claimed) == num_tasks, f"Expected {num_tasks} claims, got {len(claimed)}"
        assert len(empty) == num_workers - num_tasks

        claimed_ids = [r[2]["task"]["id"] for r in claimed]
        assert len(set(claimed_ids)) == num_tasks, f"Duplicate task claims detected: {claimed_ids}"

        execute_write("DELETE FROM tasks WHERE project_key = ?", (test_proj,))
        execute_write("DELETE FROM workers WHERE id LIKE 'w_race_h_%'")
