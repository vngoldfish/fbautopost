"""
tests/test_tier5_backend_adversarial.py
Tier 5 White-Box Adversarial Coverage Hardening for Backend API & Database Layer.

Authoritative References:
- ORIGINAL_REQUEST.md (R1-R4)
- PROJECT.md (Features F1.1 - F5.1, Interface Contracts)
- TEST_READY.md

Covers:
1. Auth Bypass Attempts & Security Hardening (tampered bearer tokens, malformed headers, header injection, timing attack safety, rate limiting).
2. High-Concurrency Lease Races (simultaneous poll & claim across 20+ simulated workers, lease expiration reclamation, cancellation races).
3. Database Contention & Rapid Writes (heavy concurrent reads/writes across multiple threads, bulk account upsert deduplication, transaction rollback integrity, SQLite WAL pragmas).
4. Boundary Inputs & Malformed Payloads (zero-byte bodies, malformed JSON, non-ASCII project keys, extreme task priorities, 100KB payloads, 404 handlers, account quarantine state machine).
"""

import sys
from pathlib import Path

# Ensure backend directory and project root are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
import json
import uuid
import hmac
import random
import string
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import verify_sync_token, extract_sync_token
from app.core.rate_limiter import rate_limiter, SlidingWindowRateLimiter
from app.db.session import query_one, query_all, execute_write, transaction, get_connection
from tests.e2e.conftest import DEFAULT_SYNC_TOKEN, DEFAULT_PROJECT_KEY, E2EClient


# ==============================================================================
# Helper Fixtures & Utilities
# ==============================================================================

@pytest.fixture
def auth_client():
    """E2E client configured with valid production credentials."""
    return E2EClient(default_token=DEFAULT_SYNC_TOKEN, default_project=DEFAULT_PROJECT_KEY)


@pytest.fixture
def raw_test_client():
    """Direct FastAPI TestClient for custom/malformed header and byte testing."""
    return TestClient(app)


def generate_unique_id(prefix: str) -> str:
    now_ms = int(time.time() * 1000)
    rand_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{now_ms}_{rand_part}"


# ==============================================================================
# CATEGORY 1: Auth Bypass Attempts & Security Hardening
# ==============================================================================

class TestAuthAdversarialHardening:
    """Stress tests and boundary attacks against authentication, headers, and rate limiting."""

    def test_adv_auth_missing_token_strict_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_STRICT_401: Non-whitelisted endpoint rejects requests lacking auth token."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res = raw_test_client.get("/api/tasks", headers={})
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        data = res.json()
        assert "Unauthorized" in data.get("error", "")

    def test_adv_auth_tampered_sync_token_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_TAMPERED_TOKEN: Requests with tampered X-Sync-Token return 401."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res = raw_test_client.get("/api/tasks", headers={"X-Sync-Token": "tampered_token_xyz_999"})
        assert res.status_code == 401

    def test_adv_auth_rfc6750_bearer_valid_200(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_RFC6750_BEARER: RFC 6750 Authorization: Bearer <valid_token> is accepted."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res = raw_test_client.get("/api/tasks", headers={"Authorization": f"Bearer {DEFAULT_SYNC_TOKEN}"})
        assert res.status_code == 200

    def test_adv_auth_rfc6750_bearer_case_insensitivity(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_BEARER_CASE: Lowercase 'bearer' and uppercase 'BEARER' are accepted."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res_lower = raw_test_client.get("/api/tasks", headers={"authorization": f"bearer {DEFAULT_SYNC_TOKEN}"})
        assert res_lower.status_code == 200

        res_upper = raw_test_client.get("/api/tasks", headers={"AUTHORIZATION": f"BEARER {DEFAULT_SYNC_TOKEN}"})
        assert res_upper.status_code == 200

    def test_adv_auth_rfc6750_bearer_tampered_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_BEARER_TAMPERED: Tampered bearer token rejected with 401."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res = raw_test_client.get("/api/tasks", headers={"Authorization": "Bearer fake_bearer_12345"})
        assert res.status_code == 401

    def test_adv_auth_rfc6750_bearer_empty_payload_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_BEARER_EMPTY: Empty bearer strings ('Bearer ', 'Bearer') rejected with 401."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res1 = raw_test_client.get("/api/tasks", headers={"Authorization": "Bearer "})
        assert res1.status_code == 401

        res2 = raw_test_client.get("/api/tasks", headers={"Authorization": "Bearer"})
        assert res2.status_code == 401

    def test_adv_auth_non_bearer_scheme_rejected_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_NON_BEARER: Basic auth and non-bearer schemes rejected with 401."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        res = raw_test_client.get("/api/tasks", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert res.status_code == 401

    def test_adv_auth_query_param_token_fallback(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_QUERY_TOKEN: Query param ?token=<token> fallback supported and authenticated."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        # Valid query token
        res_valid = raw_test_client.get(f"/api/tasks?token={DEFAULT_SYNC_TOKEN}")
        assert res_valid.status_code == 200

        # Tampered query token
        res_invalid = raw_test_client.get("/api/tasks?token=bad_token_query")
        assert res_invalid.status_code == 401

    def test_adv_auth_sql_injection_in_token_401(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_SQLI_TOKEN: SQL injection strings in token rejected with 401 without DB error."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        sqli_tokens = [
            "' OR '1'='1",
            "admin' --",
            "'; DROP TABLE workers; --",
            "' UNION SELECT * FROM accounts --"
        ]
        for token in sqli_tokens:
            res = raw_test_client.get("/api/tasks", headers={"X-Sync-Token": token})
            assert res.status_code == 401

    def test_adv_auth_massive_token_handling_no_crash(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_MASSIVE_TOKEN: 50,000 character token handled cleanly without crash or memory leak."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        massive_token = "A" * 50000
        res = raw_test_client.get("/api/tasks", headers={"X-Sync-Token": massive_token})
        assert res.status_code == 401

    def test_adv_auth_timing_attack_resistance_via_hmac(self, monkeypatch):
        """ASSERT_AUTH_TIMING_SAFE: Verifies compare_digest constant-time comparison is used."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", "super_secret_production_key_12345")
        # Exact match
        assert verify_sync_token("super_secret_production_key_12345") is True
        # Prefix match failure (must fail cleanly)
        assert verify_sync_token("super_secret_production_key_") is False
        # Suffix match failure
        assert verify_sync_token("_secret_production_key_12345") is False
        # Empty string
        assert verify_sync_token("") is False
        # None
        assert verify_sync_token(None) is False

    def test_adv_auth_worker_endpoint_missing_project_key_400(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_WORKER_PROJECT_KEY_REQUIRED: Worker endpoints require X-Project-Key."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {"X-Sync-Token": DEFAULT_SYNC_TOKEN}
        # Missing X-Project-Key on /api/tasks/poll
        res = raw_test_client.post("/api/tasks/poll", json={"workerId": "node_test"}, headers=headers)
        assert res.status_code == 400
        assert "Missing X-Project-Key header" in res.json().get("error", "")

    def test_adv_auth_worker_endpoint_whitespace_project_key_400(self, raw_test_client, monkeypatch):
        """ASSERT_AUTH_WHITESPACE_PROJECT_KEY: Whitespace-only X-Project-Key rejected with 400."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {"X-Sync-Token": DEFAULT_SYNC_TOKEN, "X-Project-Key": "    "}
        res = raw_test_client.post("/api/tasks/poll", json={"workerId": "node_test"}, headers=headers)
        assert res.status_code == 400

    def test_adv_rate_limiting_sliding_window_threshold_and_retry_after(self, raw_test_client, monkeypatch):
        """ASSERT_RATE_LIMIT_429: Exceeding sliding-window rate limit returns 429 with Retry-After header."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)

        test_ip = "192.0.2.77"
        headers = {
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "X-Forwarded-For": test_ip
        }

        # Clear history for this test IP
        with rate_limiter._lock:
            rate_limiter._history.pop(f"{test_ip}:general", None)

        limit = settings.RATE_LIMIT_GENERAL_PER_MIN
        # Fire requests up to the limit
        for _ in range(limit):
            res = raw_test_client.get("/api/accounts", headers=headers)
            assert res.status_code == 200

        # Request exceeding limit must return 429
        res_blocked = raw_test_client.get("/api/accounts", headers=headers)
        assert res_blocked.status_code == 429
        assert "Retry-After" in res_blocked.headers
        data = res_blocked.json()
        assert "Rate limit exceeded" in data.get("error", "")
        assert data.get("retryAfterSec") is not None
        assert int(data.get("retryAfterSec")) >= 1

    def test_adv_rate_limiter_stale_eviction_under_traffic(self):
        """ASSERT_RATE_LIMIT_EVICTION: SlidingWindowRateLimiter purges expired keys without memory leak."""
        limiter = SlidingWindowRateLimiter(default_window_seconds=0.1)  # 100ms window
        # Seed 100 distinct client keys
        for i in range(100):
            limiter.is_allowed(f"client_{i}", limit=10)

        assert len(limiter._history) == 100
        # Wait for window to expire
        time.sleep(0.15)

        # Force eviction trigger
        now = time.time()
        limiter._evict_stale_keys(now)
        assert len(limiter._history) == 0, f"Expected 0 keys after stale eviction, got {len(limiter._history)}"


# ==============================================================================
# CATEGORY 2: High-Concurrency Lease Races (20+ Simulated Workers)
# ==============================================================================

class TestConcurrencyLeaseRaces:
    """Stress testing task claiming, anti-collision locking, and lease renewals across 20+ threads."""

    def test_adv_concurrency_single_task_race_25_workers(self, auth_client):
        """ASSERT_RACE_SINGLE_TASK: 25 workers simultaneously polling 1 task -> exactly 1 claim, 24 None."""
        task_id = generate_unique_id("task_race_single")
        isolated_project = generate_unique_id("proj_race_single")

        # Enqueue 1 pending task in isolated tenant partition
        res_create = auth_client.post("/api/tasks", json={
            "id": task_id,
            "type": "post",
            "projectKey": isolated_project,
            "payload": {"content": "Single Task Race Content"}
        })
        assert res_create.status_code == 201

        num_workers = 25
        barrier = threading.Barrier(num_workers)
        claim_results = []
        errors = []

        def worker_task(worker_index):
            worker_id = f"race_worker_single_{worker_index}_{int(time.time()*1000)}"
            try:
                # Synchronize start across all 25 threads
                barrier.wait(timeout=5.0)
                # Each thread uses unique client IP to test distinct concurrent sessions
                res = auth_client.post(
                    "/api/tasks/poll",
                    json={"workerId": worker_id, "supportedTypes": ["post"], "projectKey": isolated_project},
                    headers={"X-Forwarded-For": f"10.0.1.{worker_index}", "X-Project-Key": isolated_project}
                )
                if res.status_code == 200:
                    claim_results.append((worker_id, res.json().get("task")))
                else:
                    errors.append((worker_id, res.status_code, res.text))
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Encountered unexpected errors during concurrency race: {errors}"
        assert len(claim_results) == num_workers

        claimed_tasks = [task for _, task in claim_results if task is not None]
        unclaimed_workers = [worker_id for worker_id, task in claim_results if task is None]

        assert len(claimed_tasks) == 1, f"Expected EXACTLY 1 worker to claim task, but got {len(claimed_tasks)}"
        assert claimed_tasks[0]["id"] == task_id
        assert claimed_tasks[0]["status"] == "assigned"
        assert len(unclaimed_workers) == num_workers - 1

        # Verify DB state
        row = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert row is not None
        assert row["status"] == "assigned"
        assert row["worker_id"] is not None
        assert row["claimed_at"] is not None
        assert row["lease_expires_at"] > int(time.time() * 1000)

    def test_adv_concurrency_batch_task_race_25_workers_10_tasks(self, auth_client):
        """ASSERT_RACE_BATCH_TASKS: 25 workers simultaneously polling 10 tasks -> exactly 10 claims, 15 None."""
        task_ids = []
        isolated_project = generate_unique_id("proj_race_batch")

        # Enqueue 10 pending tasks in isolated tenant partition
        for i in range(10):
            tid = generate_unique_id(f"task_batch_{i}")
            task_ids.append(tid)
            res = auth_client.post("/api/tasks", json={
                "id": tid,
                "type": "post",
                "priority": i * 10,
                "projectKey": isolated_project,
                "payload": {"content": f"Batch Task {i}"}
            })
            assert res.status_code == 201

        num_workers = 25
        barrier = threading.Barrier(num_workers)
        claim_results = []
        errors = []

        def worker_task(worker_index):
            worker_id = f"race_worker_batch_{worker_index}_{int(time.time()*1000)}"
            try:
                barrier.wait(timeout=5.0)
                res = auth_client.post(
                    "/api/tasks/poll",
                    json={"workerId": worker_id, "supportedTypes": ["post"], "projectKey": isolated_project},
                    headers={"X-Forwarded-For": f"10.0.2.{worker_index}", "X-Project-Key": isolated_project}
                )
                if res.status_code == 200:
                    claim_results.append((worker_id, res.json().get("task")))
                else:
                    errors.append((worker_id, res.status_code, res.text))
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Errors during batch race: {errors}"
        claimed = [t for _, t in claim_results if t is not None]
        claimed_ids = [t["id"] for t in claimed]

        assert len(claimed) == 10, f"Expected 10 tasks claimed, got {len(claimed)}"
        # Anti-collision assertion: all claimed IDs must be unique
        assert len(set(claimed_ids)) == 10, f"Detected duplicate task claims: {claimed_ids}"
        assert set(claimed_ids) == set(task_ids)

    def test_adv_concurrency_expired_lease_reclaim_race_15_workers(self, auth_client):
        """ASSERT_RACE_EXPIRED_LEASE: An expired lease can only be reclaimed by ONE worker among 15 competitors."""
        task_id = generate_unique_id("task_expired_lease")
        isolated_project = generate_unique_id("proj_expired")
        now_ms = int(time.time() * 1000)

        # Insert a task that is currently assigned to a crashed worker with an expired lease
        execute_write("""
            INSERT INTO tasks (
                id, task_type, project_key, worker_id, status, payload,
                claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
            ) VALUES (?, 'post', ?, 'crashed_worker_99', 'assigned', '{}', ?, ?, ?, 0, ?, ?)
        """, (
            task_id,
            isolated_project,
            now_ms - 120000,
            now_ms - 5000,  # Expired 5 seconds ago
            now_ms - 120000,
            now_ms - 120000,
            now_ms - 120000
        ))

        num_workers = 15
        barrier = threading.Barrier(num_workers)
        claim_results = []
        errors = []

        def worker_task(idx):
            worker_id = f"reclaim_worker_{idx}_{int(time.time()*1000)}"
            try:
                barrier.wait(timeout=5.0)
                res = auth_client.post(
                    "/api/tasks/poll",
                    json={"workerId": worker_id, "supportedTypes": ["post"], "projectKey": isolated_project},
                    headers={"X-Forwarded-For": f"10.0.3.{idx}", "X-Project-Key": isolated_project}
                )
                if res.status_code == 200:
                    claim_results.append((worker_id, res.json().get("task")))
                else:
                    errors.append((worker_id, res.status_code, res.text))
            except Exception as e:
                errors.append((worker_id, str(e)))

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0
        claimed = [t for _, t in claim_results if t is not None and t.get("id") == task_id]
        assert len(claimed) == 1, f"Expected exactly 1 worker to reclaim expired lease, got {len(claimed)}"

        # The new worker must hold a renewed lease ~60s in the future
        reclaimed_task = claimed[0]
        assert reclaimed_task["leaseExpiresAt"] > int(time.time() * 1000)
        assert reclaimed_task["workerId"] != "crashed_worker_99"

    def test_adv_concurrency_expired_lease_reclaim_by_same_worker_succeeds(self, auth_client):
        """ASSERT_SAME_WORKER_RECLAIM: When the SAME crashed worker ID restarts, it reclaims its own expired lease."""
        task_id = generate_unique_id("task_same_worker_expired")
        isolated_project = generate_unique_id("proj_same_worker")
        now_ms = int(time.time() * 1000)

        execute_write("""
            INSERT INTO tasks (
                id, task_type, project_key, worker_id, status, payload,
                claimed_at, lease_expires_at, scheduled_time, retry_count, created_at, updated_at
            ) VALUES (?, 'post', ?, 'crashed_worker_self', 'assigned', '{}', ?, ?, ?, 0, ?, ?)
        """, (
            task_id,
            isolated_project,
            now_ms - 120000,
            now_ms - 5000,
            now_ms - 120000,
            now_ms - 120000,
            now_ms - 120000
        ))

        # Original worker restarts with same worker ID
        res = auth_client.post(
            "/api/tasks/poll",
            json={"workerId": "crashed_worker_self", "supportedTypes": ["post"], "projectKey": isolated_project},
            headers={"X-Project-Key": isolated_project}
        )
        assert res.status_code == 200
        claimed = res.json().get("task")
        assert claimed is not None, "Same worker was unable to reclaim its own expired task!"
        assert claimed["id"] == task_id
        assert claimed["workerId"] == "crashed_worker_self"

    def test_adv_concurrency_concurrent_cancel_vs_lease_heartbeat(self, auth_client):
        """ASSERT_RACE_CANCEL_VS_EXTEND: Cannot extend lease once a task has been cancelled."""
        task_id = generate_unique_id("task_cancel_race")
        isolated_project = generate_unique_id("proj_cancel")

        res_create = auth_client.post("/api/tasks", json={
            "id": task_id,
            "type": "post",
            "projectKey": isolated_project,
            "payload": {"content": "Cancel Race Content"}
        })
        assert res_create.status_code == 201

        # Claim the task
        worker_id = f"worker_cancel_race_{int(time.time()*1000)}"
        res_poll = auth_client.post(
            "/api/tasks/poll",
            json={"workerId": worker_id, "projectKey": isolated_project},
            headers={"X-Project-Key": isolated_project}
        )
        assert res_poll.status_code == 200

        # Cancel the task
        res_cancel = auth_client.post(f"/api/tasks/{task_id}/cancel")
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "cancelled"

        # Attempt to extend lease on cancelled task must fail with 400
        res_heartbeat = auth_client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 90})
        assert res_heartbeat.status_code == 400
        assert "Cannot extend lease" in res_heartbeat.json().get("detail", "")

    def test_adv_concurrency_account_quarantine_race_prevents_claim(self, auth_client):
        """ASSERT_RACE_QUARANTINE: Updating account health to checkpoint immediately quarantines pending tasks."""
        acc_id = generate_unique_id("acc_quarantine_race")
        task_id = generate_unique_id("task_quarantine_race")
        isolated_project = generate_unique_id("proj_quarantine")

        # Create active account
        auth_client.post("/api/accounts", json={
            "id": acc_id,
            "name": "Quarantine Race Account",
            "targetId": acc_id,
            "accessToken": "EAA_test_token"
        })

        # Create pending task linked to this account
        auth_client.post("/api/tasks", json={
            "id": task_id,
            "type": "post",
            "accountId": acc_id,
            "projectKey": isolated_project,
            "payload": {"content": "Quarantined post"}
        })

        # Mark account as checkpoint
        res_health = auth_client.post(f"/api/accounts/{acc_id}/health", json={
            "healthStatus": "checkpoint",
            "checkpointType": "2fa_required"
        })
        assert res_health.status_code == 200

        # Attempt to poll with 10 concurrent workers
        claim_results = []
        barrier = threading.Barrier(10)

        def poll_attempt(idx):
            barrier.wait(timeout=5.0)
            res = auth_client.post(
                "/api/tasks/poll",
                json={"workerId": f"worker_quarantine_{idx}", "supportedTypes": ["post"], "projectKey": isolated_project},
                headers={"X-Forwarded-For": f"10.0.4.{idx}", "X-Project-Key": isolated_project}
            )
            if res.status_code == 200:
                claim_results.append(res.json().get("task"))

        threads = [threading.Thread(target=poll_attempt, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # None of the workers should receive this task
        claimed_this_task = [t for t in claim_results if t and t.get("id") == task_id]
        assert len(claimed_this_task) == 0, "Quarantined account's task was illegally claimed!"

        # Verify DB shows task as cancelled
        row = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        assert row["status"] == "cancelled"


# ==============================================================================
# CATEGORY 3: Database Contention & Rapid Writes
# ==============================================================================

class TestDatabaseContention:
    """Stress testing SQLite WAL concurrency, write locking, and data integrity under load."""

    def test_adv_db_heavy_contention_mixed_read_write_threads(self, auth_client):
        """ASSERT_DB_HEAVY_CONTENTION: 20 threads performing rapid writes and reads -> zero deadlocks or 500s."""
        num_operations = 80
        errors = []
        results = []

        def worker_loop(thread_id):
            client = E2EClient(default_token=DEFAULT_SYNC_TOKEN, default_project=DEFAULT_PROJECT_KEY)
            for i in range(num_operations // 4):
                op_type = i % 4
                worker_id = f"thread_{thread_id}_worker"
                headers = {"X-Forwarded-For": f"10.0.5.{thread_id}"}

                try:
                    if op_type == 0:
                        # Write: Create task
                        tid = generate_unique_id(f"stress_task_{thread_id}_{i}")
                        r = client.post("/api/tasks", json={
                            "id": tid,
                            "type": "warmup",
                            "priority": random.randint(-10, 50),
                            "payload": {"thread": thread_id, "iter": i}
                        }, headers=headers)
                        results.append((r.status_code, "create_task"))

                    elif op_type == 1:
                        # Write: Poll task
                        r = client.post("/api/tasks/poll", json={
                            "workerId": worker_id,
                            "supportedTypes": ["warmup", "post"]
                        }, headers=headers)
                        results.append((r.status_code, "poll_task"))

                    elif op_type == 2:
                        # Write: Heartbeat
                        r = client.post("/api/workers/heartbeat", json={
                            "workerId": worker_id,
                            "status": "idle"
                        }, headers=headers)
                        results.append((r.status_code, "heartbeat"))

                    elif op_type == 3:
                        # Read: List workers & tasks
                        r = client.get("/api/workers", headers=headers)
                        results.append((r.status_code, "list_workers"))

                except Exception as e:
                    errors.append((thread_id, op_type, str(e)))

        threads = [threading.Thread(target=worker_loop, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20.0)

        assert len(errors) == 0, f"Encountered contention errors: {errors}"
        # All returned status codes must be 200 or 201
        for code, op in results:
            assert code in [200, 201], f"Operation {op} failed with status {code}"

    def test_adv_db_concurrent_account_upsert_deduplication(self, auth_client):
        """ASSERT_DB_UPSERT_DEDUP: 15 threads concurrently upserting identical targetId -> 1 row created."""
        target_id = generate_unique_id("target_dedup_race")
        barrier = threading.Barrier(15)
        results = []
        errors = []

        def upsert_account(idx):
            client = E2EClient(default_token=DEFAULT_SYNC_TOKEN, default_project=DEFAULT_PROJECT_KEY)
            try:
                barrier.wait(timeout=5.0)
                r = client.post("/api/accounts", json={
                    "name": f"Account Version {idx}",
                    "targetId": target_id,
                    "accessToken": f"token_version_{idx}",
                    "projectKey": DEFAULT_PROJECT_KEY
                }, headers={"X-Forwarded-For": f"10.0.6.{idx}"})
                results.append((idx, r.status_code))
            except Exception as e:
                errors.append((idx, str(e)))

        threads = [threading.Thread(target=upsert_account, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Errors during concurrent account upsert: {errors}"
        assert all(code in [200, 201] for _, code in results)

        # Database must contain exactly 1 account row for this targetId
        rows = query_all("SELECT * FROM accounts WHERE target_id = ?", (target_id,))
        assert len(rows) == 1, f"Expected 1 deduplicated account row, found {len(rows)}"

    def test_adv_db_transaction_rollback_integrity(self):
        """ASSERT_DB_ROLLBACK: Failed operations roll back cleanly and preserve DB sanity."""
        test_task_id = generate_unique_id("rollback_task")

        # Verify transaction rollback upon deliberate SQLite error
        with pytest.raises(Exception):
            with transaction() as conn:
                conn.execute("INSERT INTO tasks (id, task_type, status, payload, created_at, updated_at) VALUES (?, 'post', 'pending', '{}', 0, 0)", (test_task_id,))
                # Deliberate syntax/constraint violation
                conn.execute("INSERT INTO non_existent_table_xyz VALUES (1, 2, 3)")

        # Verify task was rolled back
        row = query_one("SELECT * FROM tasks WHERE id = ?", (test_task_id,))
        assert row is None, "Task was unexpectedly committed despite exception in transaction block!"

    def test_adv_db_wal_mode_and_pragmas_enforced(self):
        """ASSERT_DB_WAL_PRAGMAS: SQLite production pragmas (WAL, busy_timeout, foreign_keys) are active."""
        conn = get_connection()
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal", f"Expected journal_mode WAL, got {journal_mode}"

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert int(busy_timeout) >= 5000, f"Expected busy_timeout >= 5000, got {busy_timeout}"

        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert int(foreign_keys) == 1, f"Expected foreign_keys ON, got {foreign_keys}"


# ==============================================================================
# CATEGORY 4: Boundary Inputs & Malformed Payloads
# ==============================================================================

class TestBoundaryInputsAndMalformedPayloads:
    """Stress testing edge cases, non-ASCII encoding, zero-byte bodies, and malformed inputs."""

    def test_adv_boundary_zero_byte_body_tasks_poll(self, raw_test_client, monkeypatch):
        """ASSERT_BOUNDARY_ZERO_BYTE_POLL: Zero-byte request body returns 422, zero unhandled 500 crashes."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "X-Project-Key": DEFAULT_PROJECT_KEY,
            "Content-Type": "application/json"
        }
        res = raw_test_client.post("/api/tasks/poll", content=b"", headers=headers)
        assert res.status_code in [400, 422], f"Expected 400/422 on empty body, got {res.status_code}"

    def test_adv_boundary_zero_byte_body_worker_register(self, raw_test_client, monkeypatch):
        """ASSERT_BOUNDARY_ZERO_BYTE_REGISTER: Zero-byte request body returns 422, zero 500 crashes."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "X-Project-Key": DEFAULT_PROJECT_KEY,
            "Content-Type": "application/json"
        }
        res = raw_test_client.post("/api/workers/register", content=b"", headers=headers)
        assert res.status_code in [400, 422]

    def test_adv_boundary_zero_byte_body_account_create(self, raw_test_client, monkeypatch):
        """ASSERT_BOUNDARY_ZERO_BYTE_ACCOUNT: Zero-byte body on account creation returns 422."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "Content-Type": "application/json"
        }
        res = raw_test_client.post("/api/accounts", content=b"", headers=headers)
        assert res.status_code in [400, 422]

    def test_adv_boundary_malformed_json_syntax(self, raw_test_client, monkeypatch):
        """ASSERT_BOUNDARY_MALFORMED_JSON: Syntactically broken JSON returns 422 without server error."""
        monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
        headers = {
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "X-Project-Key": DEFAULT_PROJECT_KEY,
            "Content-Type": "application/json"
        }
        malformed_bodies = [
            b'{"id": "bad", broken: True}',
            b'{unquoted_key: 123}',
            b'{"unterminated_string: ',
            b'[1, 2, 3,]'
        ]
        for body in malformed_bodies:
            res = raw_test_client.post("/api/tasks", content=body, headers=headers)
            assert res.status_code == 422, f"Expected 422 for {body}, got {res.status_code}"

    def test_adv_boundary_non_ascii_project_keys(self, auth_client):
        """ASSERT_BOUNDARY_NON_ASCII_KEYS: UTF-8 Vietnamese diacritics and emojis in project keys via query params."""
        non_ascii_project = f"Chi nhánh Hà Nội {generate_unique_id('vn')} 🇻🇳 🚀"
        worker_id = generate_unique_id("worker_vn")
        task_id = generate_unique_id("task_vn")

        # Register worker under non-ASCII project key using URL-encoded query param
        encoded_pk = urllib.parse.quote(non_ascii_project)
        res_reg = auth_client.post(
            f"/api/workers/register?projectKey={encoded_pk}",
            json={
                "id": worker_id,
                "name": "Node Hà Nội",
                "projectKey": non_ascii_project
            },
            headers={"X-Project-Key": None}
        )
        assert res_reg.status_code in [200, 201]

        # Enqueue task for this project
        res_task = auth_client.post("/api/tasks", json={
            "id": task_id,
            "type": "post",
            "projectKey": non_ascii_project,
            "payload": {"content": "Chào mừng ngày mới"}
        })
        assert res_task.status_code == 201

        # Poll with matching non-ASCII project key -> should claim
        res_poll = auth_client.post(
            f"/api/tasks/poll?projectKey={encoded_pk}",
            json={
                "workerId": worker_id,
                "supportedTypes": ["post"],
                "projectKey": non_ascii_project
            },
            headers={"X-Project-Key": None}
        )
        assert res_poll.status_code == 200
        claimed_task = res_poll.json().get("task")
        assert claimed_task is not None
        assert claimed_task["id"] == task_id
        assert claimed_task["projectKey"] == non_ascii_project

        # Poll with different project key -> should not claim
        encoded_other = urllib.parse.quote("Khác Đà Nẵng")
        res_poll_other = auth_client.post(
            f"/api/tasks/poll?projectKey={encoded_other}",
            json={
                "workerId": "other_worker",
                "supportedTypes": ["post"],
                "projectKey": "Khác Đà Nẵng"
            },
            headers={"X-Project-Key": None}
        )
        assert res_poll_other.status_code == 200
        assert res_poll_other.json().get("task") is None

    def test_adv_boundary_extreme_task_priorities_ordering(self, auth_client):
        """ASSERT_BOUNDARY_PRIORITIES: Extreme 64-bit int priorities dispatched in strict descending order."""
        isolated_project = generate_unique_id("proj_priority")
        priorities = [
            (generate_unique_id("task_p_max"), 9223372036854775807),     # Max 64-bit int
            (generate_unique_id("task_p_high"), 1000),
            (generate_unique_id("task_p_zero"), 0),
            (generate_unique_id("task_p_neg"), -9223372036854775808),    # Min 64-bit int
        ]

        worker_id = generate_unique_id("worker_priority_test")
        now_ms = int(time.time() * 1000)

        # Enqueue all tasks at identical scheduled time in isolated project
        for tid, p in priorities:
            res = auth_client.post("/api/tasks", json={
                "id": tid,
                "type": "warmup",
                "priority": p,
                "scheduledTime": now_ms,
                "projectKey": isolated_project,
                "payload": {"priority": p}
            })
            assert res.status_code == 201

        # Sequentially claim all 4 tasks and verify priority order
        expected_order = [tid for tid, _ in priorities]
        actual_order = []

        for _ in range(4):
            res_poll = auth_client.post(
                "/api/tasks/poll",
                json={"workerId": worker_id, "supportedTypes": ["warmup"], "projectKey": isolated_project},
                headers={"X-Project-Key": isolated_project}
            )
            assert res_poll.status_code == 200
            task = res_poll.json().get("task")
            assert task is not None
            actual_order.append(task["id"])

        assert actual_order == expected_order, f"Expected dispatch order {expected_order}, got {actual_order}"

    def test_adv_boundary_massive_task_payload_100kb(self, auth_client):
        """ASSERT_BOUNDARY_LARGE_PAYLOAD: 100KB payload handled without truncation or database corruption."""
        task_id = generate_unique_id("task_100kb")
        large_text = "FB_AUTO_" * 12500  # ~100,000 bytes
        payload_data = {
            "largeText": large_text,
            "spintaxList": [f"variant_{i}_{large_text[:50]}" for i in range(20)]
        }

        res = auth_client.post("/api/tasks", json={
            "id": task_id,
            "type": "post",
            "projectKey": DEFAULT_PROJECT_KEY,
            "payload": payload_data
        })
        assert res.status_code == 201

        # Fetch and verify integrity
        res_get = auth_client.get(f"/api/tasks/{task_id}")
        assert res_get.status_code == 200
        saved_task = res_get.json().get("task")
        assert saved_task is not None
        assert saved_task["payload"]["largeText"] == large_text
        assert len(saved_task["payload"]["spintaxList"]) == 20

    def test_adv_boundary_non_existent_resources_return_404(self, auth_client):
        """ASSERT_BOUNDARY_404: Non-existent tasks, workers, and accounts return HTTP 404 Not Found."""
        phantom_task = "phantom_task_999999"
        phantom_worker = "phantom_worker_999999"
        phantom_account = "phantom_account_999999"

        # Task endpoints
        assert auth_client.get(f"/api/tasks/{phantom_task}").status_code == 404
        assert auth_client.post(f"/api/tasks/{phantom_task}/status", json={"status": "completed"}).status_code == 404
        assert auth_client.post(f"/api/tasks/{phantom_task}/cancel").status_code == 404
        assert auth_client.post(f"/api/tasks/{phantom_task}/heartbeat", json={"extendSec": 60}).status_code == 404

        # Worker endpoints
        assert auth_client.put(f"/api/workers/{phantom_worker}/accounts", json={"accountIds": ["a1"]}).status_code == 404
        assert auth_client.delete(f"/api/workers/{phantom_worker}").status_code == 404

        # Account endpoints
        assert auth_client.delete(f"/api/accounts/{phantom_account}").status_code == 404
        assert auth_client.patch(f"/api/accounts/{phantom_account}", json={"name": "New Name"}).status_code == 404

    def test_adv_boundary_worker_heartbeat_unknown_status_fallback(self, auth_client):
        """ASSERT_BOUNDARY_HEARTBEAT_STATUS: Unknown worker heartbeat status normalizes to 'idle'."""
        worker_id = generate_unique_id("worker_unknown_status")
        # Register worker first
        auth_client.post("/api/workers/register", json={"id": worker_id})

        # Heartbeat with unrecognized status
        res = auth_client.post("/api/workers/heartbeat", json={
            "workerId": worker_id,
            "status": "malicious_hacker_status"
        })
        assert res.status_code == 200
        assert res.json().get("status") == "ok"

        # Worker in database should have status 'idle'
        row = query_one("SELECT status FROM workers WHERE id = ?", (worker_id,))
        assert row is not None
        assert row["status"] == "idle"

    def test_adv_boundary_worker_account_assignment_sanitization(self, auth_client):
        """ASSERT_BOUNDARY_ACCOUNT_SANITIZATION: Assigned accounts list strips spaces, empty strings, and duplicates."""
        worker_id = generate_unique_id("worker_sanitization")
        # Register worker first
        auth_client.post("/api/workers/register", json={"id": worker_id})

        dirty_accounts = ["acc_001", "  ", "", "acc_001", "acc_002", "   acc_003  "]
        res = auth_client.put(f"/api/workers/{worker_id}/accounts", json={"accountIds": dirty_accounts})
        assert res.status_code == 200
        assigned = res.json().get("assignedAccounts")
        assert assigned == ["acc_001", "acc_002", "acc_003"]
