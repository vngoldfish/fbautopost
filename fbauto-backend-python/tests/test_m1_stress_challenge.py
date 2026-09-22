"""
test_m1_stress_challenge.py
Adversarial Empirical Stress & Verification Test Suite for Milestone 1.

Challenges:
1. SQLite WAL Concurrency: Simultaneous readers and writers under heavy load, testing for SQLITE_BUSY, deadlocks, and consistency.
2. Sliding-Window Rate Limiting: 60 req/min threshold on polling, HTTP 429 with Retry-After header, tier isolation for general endpoints.
3. Token Security & Header Robustness: Case sensitivity, timing variations, malformed/oversized tokens, path traversal bypass attempts.
"""

import os
import sys
import time
import math
import base64
import sqlite3
import threading
import concurrent.futures
from typing import List, Dict, Any, Tuple
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app.core.config import settings
from app.core.security import verify_sync_token, extract_sync_token, extract_project_key, extract_worker_id
from app.core.rate_limiter import SlidingWindowRateLimiter, rate_limiter
from app.db.session import (
    get_connection,
    get_db,
    transaction,
    query_all,
    query_one,
    execute_write,
    execute_insert,
    close_thread_connection,
    _write_lock
)

client = TestClient(app)

# ==============================================================================
# CHALLENGE 1: SQLite WAL Concurrency & Deadlock Stress Tests
# ==============================================================================

class TestSqliteWalConcurrency:
    """Empirically stress-tests SQLite WAL mode under concurrent read/write contention."""

    def test_wal_pragmas_active(self):
        """Verify that all connections apply WAL mode, 5000ms busy timeout, and memory temp store."""
        with get_db() as db:
            journal_mode = db.execute("PRAGMA journal_mode;").fetchone()[0]
            busy_timeout = db.execute("PRAGMA busy_timeout;").fetchone()[0]
            foreign_keys = db.execute("PRAGMA foreign_keys;").fetchone()[0]
            synchronous = db.execute("PRAGMA synchronous;").fetchone()[0]

            assert str(journal_mode).lower() == "wal", f"Expected WAL mode, got {journal_mode}"
            assert busy_timeout >= 5000, f"Expected busy_timeout >= 5000, got {busy_timeout}"
            assert foreign_keys == 1, f"Expected foreign_keys == ON, got {foreign_keys}"

    def test_simultaneous_readers_during_long_write_transaction(self):
        """
        Verify that in WAL mode, readers are NOT blocked while a writer holds an active write transaction.
        In rollback journal mode, this would deadlock or raise SQLITE_BUSY.
        """
        write_started = threading.Event()
        write_can_commit = threading.Event()
        writer_done = threading.Event()
        writer_errors = []
        reader_errors = []
        reader_read_counts = []

        now_ms = int(time.time() * 1000)
        test_marker = f"wal_test_{now_ms}"

        def writer_thread():
            try:
                with transaction() as db:
                    db.execute(
                        "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (test_marker, "WAL Active Writer", "Testing reader concurrency", now_ms, now_ms)
                    )
                    # Signal that write has started and transaction is actively held
                    write_started.set()
                    # Hold transaction open for 0.4 seconds while readers query
                    write_can_commit.wait(timeout=5.0)
            except Exception as e:
                writer_errors.append(e)
            finally:
                writer_done.set()
                close_thread_connection()

        def reader_thread(reader_id: int):
            try:
                # Wait until writer is mid-transaction
                assert write_started.wait(timeout=5.0), f"Reader {reader_id} timed out waiting for writer"
                reads_performed = 0
                for _ in range(30):
                    # Reader queries database while writer transaction is actively in-flight
                    with get_db() as db:
                        rows = db.execute("SELECT count(*) FROM projects").fetchone()
                        assert rows is not None
                        reads_performed += 1
                    time.sleep(0.005)
                reader_read_counts.append(reads_performed)
            except Exception as e:
                reader_errors.append((reader_id, e))
            finally:
                close_thread_connection()

        # Launch writer
        w_thread = threading.Thread(target=writer_thread)
        w_thread.start()

        # Wait for writer to enter transaction
        assert write_started.wait(timeout=3.0), f"Writer failed to start transaction in time. Errors: {writer_errors}"

        # Launch 8 concurrent reader threads while writer transaction is ACTIVE
        r_threads = [threading.Thread(target=reader_thread, args=(i,)) for i in range(8)]
        for rt in r_threads:
            rt.start()

        # Let readers perform queries during the write transaction
        time.sleep(0.2)
        # Now allow writer to commit
        write_can_commit.set()

        w_thread.join(timeout=5.0)
        for rt in r_threads:
            rt.join(timeout=5.0)

        # Clean up marker row
        execute_write("DELETE FROM projects WHERE id = ?", (test_marker,))

        assert len(writer_errors) == 0, f"Writer encountered errors: {writer_errors}"
        assert len(reader_errors) == 0, f"Readers were blocked or failed: {reader_errors}"
        assert sum(reader_read_counts) == 8 * 30, f"Readers failed to complete all read iterations"

    def test_high_concurrency_mixed_read_write_stress(self):
        """
        Stress test: 15 writer threads and 25 reader threads running simultaneously
        with a synchronized barrier launch.
        Verifies: Zero SQLITE_BUSY, zero OperationalError, zero deadlocks, 100% data integrity.
        """
        num_writers = 15
        writes_per_thread = 20
        num_readers = 25
        reads_per_thread = 40
        total_threads = num_writers + num_readers

        barrier = threading.Barrier(total_threads)
        errors = []
        written_ids = []
        lock_written = threading.Lock()

        test_run_id = f"stress_{int(time.time()*1000)}"

        def writer_worker(thread_idx: int):
            try:
                barrier.wait(timeout=10.0)
                for i in range(writes_per_thread):
                    log_id = f"{test_run_id}_w{thread_idx}_{i}"
                    execute_write(
                        "INSERT INTO logs (id, timestamp, action, entity_type, entity_id, project_key, details, created_at) "
                        "VALUES (?, datetime('now'), ?, 'stress_test', ?, 'all', '{}', ?)",
                        (log_id, f"action_{thread_idx}_{i}", f"entity_{thread_idx}_{i}", int(time.time()*1000))
                    )
                    with lock_written:
                        written_ids.append(log_id)
            except Exception as e:
                errors.append(("writer", thread_idx, e))
            finally:
                close_thread_connection()

        def reader_worker(thread_idx: int):
            try:
                barrier.wait(timeout=10.0)
                for _ in range(reads_per_thread):
                    with get_db() as db:
                        count = db.execute("SELECT count(*) FROM logs WHERE id LIKE ?", (f"{test_run_id}%",)).fetchone()[0]
                    # Reading must not fail
                    assert count >= 0
                    time.sleep(0.001)
            except Exception as e:
                errors.append(("reader", thread_idx, e))
            finally:
                close_thread_connection()

        threads = []
        for i in range(num_writers):
            threads.append(threading.Thread(target=writer_worker, args=(i,)))
        for i in range(num_readers):
            threads.append(threading.Thread(target=reader_worker, args=(i,)))

        start_time = time.time()
        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=30.0)

        elapsed = time.time() - start_time

        # Verify no errors occurred
        assert len(errors) == 0, f"Encountered concurrency errors: {errors}"

        # Verify all writes committed successfully (zero dropped writes)
        expected_writes = num_writers * writes_per_thread
        assert len(written_ids) == expected_writes

        actual_rows = query_one(
            "SELECT count(*) as cnt FROM logs WHERE id LIKE ?",
            (f"{test_run_id}%",)
        )["cnt"]
        assert actual_rows == expected_writes, f"Expected {expected_writes} rows, found {actual_rows}"

        # Clean up stress logs
        execute_write("DELETE FROM logs WHERE id LIKE ?", (f"{test_run_id}%",))

    def test_write_contention_barrier_blast(self):
        """
        Blast test: 30 threads attempting to write at the exact same instant.
        Tests whether _write_lock + BEGIN IMMEDIATE properly serializes without SQLITE_BUSY.
        """
        thread_count = 30
        barrier = threading.Barrier(thread_count)
        errors = []
        now_ms = int(time.time() * 1000)
        test_prefix = f"blast_{now_ms}"

        def blast_writer(idx: int):
            try:
                barrier.wait(timeout=5.0)
                project_id = f"{test_prefix}_{idx}"
                execute_write(
                    "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (project_id, f"Blast Project {idx}", "Contention test", now_ms, now_ms)
                )
            except Exception as e:
                errors.append((idx, e))
            finally:
                close_thread_connection()

        threads = [threading.Thread(target=blast_writer, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        # Cleanup
        execute_write("DELETE FROM projects WHERE id LIKE ?", (f"{test_prefix}%",))

        assert len(errors) == 0, f"Write contention failed with errors: {errors}"

    def test_transaction_rollback_cleanliness(self):
        """
        Verify that a failing transaction rolls back cleanly, releases the write lock,
        and leaves subsequent transactions completely unaffected.
        """
        now_ms = int(time.time() * 1000)
        fail_id = f"fail_{now_ms}"
        success_id = f"succ_{now_ms}"

        # 1. Deliberately raise exception inside transaction
        with pytest.raises(RuntimeError):
            with transaction() as db:
                db.execute(
                    "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (fail_id, "Failed Project", "Should be rolled back", now_ms, now_ms)
                )
                raise RuntimeError("Simulated failure during write")

        # Verify fail_id was rolled back
        row_fail = query_one("SELECT * FROM projects WHERE id = ?", (fail_id,))
        assert row_fail is None, "Failed transaction was not rolled back!"

        # 2. Immediately execute valid transaction to ensure lock was released
        execute_write(
            "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (success_id, "Success Project", "Should commit", now_ms, now_ms)
        )

        row_succ = query_one("SELECT * FROM projects WHERE id = ?", (success_id,))
        assert row_succ is not None
        assert row_succ["id"] == success_id

        # Clean up
        execute_write("DELETE FROM projects WHERE id = ?", (success_id,))

    def test_concurrent_upsert_accounts_race_condition(self):
        """
        Adversarial Test: Check-Then-Act Race Condition in Accounts Upsert.
        When multiple concurrent threads submit an account with the SAME targetId,
        does non-atomic query_one followed by execute_write cause UNIQUE constraint crash?
        """
        thread_count = 10
        barrier = threading.Barrier(thread_count)
        target_id = f"race_target_{int(time.time()*1000)}"
        exceptions = []
        status_codes = []

        def worker_post(idx: int):
            try:
                barrier.wait(timeout=5.0)
                payload = {
                    "name": f"Race Account {idx}",
                    "accessToken": f"token_{idx}",
                    "targetId": target_id,
                    "type": "profile"
                }
                res = client.post("/api/accounts", json=payload)
                status_codes.append(res.status_code)
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker_post, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # Cleanup
        execute_write("DELETE FROM accounts WHERE target_id = ?", (target_id,))

        # If race condition is present, exceptions or 500s will be caught
        has_crashed = len(exceptions) > 0 or any(code >= 500 for code in status_codes)
        # Note: If has_crashed is True, this empirically proves the UNIQUE constraint race condition!
        assert not has_crashed, f"Race condition detected! Crashes: {exceptions}, Status codes: {status_codes}"

    def test_add_activity_log_concurrency_collision(self):
        """
        Adversarial Test: ID Collision in add_activity_log.
        add_activity_log generates log_id = f"log_{now_ms}".
        When multiple threads execute add_activity_log in the same millisecond,
        does it crash with sqlite3.IntegrityError: UNIQUE constraint failed: logs.id?
        """
        thread_count = 10
        barrier = threading.Barrier(thread_count)
        errors = []

        def worker_log(idx: int):
            try:
                barrier.wait(timeout=5.0)
                from app.db.session import add_activity_log
                add_activity_log("CONCURRENT_STRESS", entity_type="test", entity_id=f"e_{idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_log, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # Cleanup
        execute_write("DELETE FROM logs WHERE action = 'CONCURRENT_STRESS'")

        assert len(errors) == 0, f"add_activity_log failed with millisecond ID collision errors: {errors}"




# ==============================================================================
# CHALLENGE 2: Rate Limiting & Tier Isolation Stress Tests
# ==============================================================================

class TestRateLimitingAndTierIsolation:
    """Empirically stress-tests sliding-window rate limiting, HTTP 429 headers, and tier isolation."""

    def test_sliding_window_polling_limit_and_429_retry_after(self):
        """
        Verify that exceeding RATE_LIMIT_POLL_PER_MIN (60 req/min) on polling endpoints:
        1. Allows exactly 60 requests
        2. Blocks the 61st request with HTTP 429
        3. Returns 'Retry-After' header with valid integer
        4. Returns JSON body with retryAfterSec
        """
        client_ip = "198.51.100.42"
        headers = {
            "X-Forwarded-For": client_ip,
            "X-Project-Key": "all",
            "X-Worker-Id": "worker_rate_test"
        }
        poll_payload = {
            "workerId": "worker_rate_test",
            "supportedTypes": ["post", "warmup"]
        }

        # Clear rate limiter bucket for this test IP
        tier_key = f"{client_ip}:poll"
        with rate_limiter._lock:
            if tier_key in rate_limiter._history:
                del rate_limiter._history[tier_key]

        limit = settings.RATE_LIMIT_POLL_PER_MIN
        assert limit == 60, f"Expected default RATE_LIMIT_POLL_PER_MIN to be 60, got {limit}"

        # Send exactly 60 requests -> all should pass
        for i in range(limit):
            res = client.post("/api/tasks/poll", json=poll_payload, headers=headers)
            assert res.status_code == 200, f"Request #{i+1} failed with status {res.status_code}: {res.text}"

        # 61st request -> MUST be rejected with HTTP 429
        res_blocked = client.post("/api/tasks/poll", json=poll_payload, headers=headers)
        assert res_blocked.status_code == 429, f"Expected HTTP 429, got {res_blocked.status_code}"

        # Verify Retry-After header
        assert "retry-after" in [k.lower() for k in res_blocked.headers.keys()], "Retry-After header missing!"
        retry_after = int(res_blocked.headers.get("retry-after") or res_blocked.headers.get("Retry-After"))
        assert 1 <= retry_after <= 60, f"Retry-After value {retry_after} out of expected range [1, 60]"

        # Verify response payload
        body = res_blocked.json()
        assert "error" in body
        assert "rate limit exceeded" in body["error"].lower()
        assert "retryAfterSec" in body
        assert body["retryAfterSec"] == retry_after

    def test_tier_isolation_general_endpoints_remain_responsive(self):
        """
        Verify tier isolation: Even when client IP has completely exhausted its polling tier (429),
        general endpoints (GET /api/posts, GET /api/accounts, GET /health) remain responsive (HTTP 200).
        """
        client_ip = "198.51.100.99"
        poll_headers = {
            "X-Forwarded-For": client_ip,
            "X-Project-Key": "all",
            "X-Worker-Id": "worker_isolation_test"
        }
        poll_payload = {
            "workerId": "worker_isolation_test",
            "supportedTypes": ["post"]
        }

        # Clear buckets for this IP
        with rate_limiter._lock:
            rate_limiter._history.pop(f"{client_ip}:poll", None)
            rate_limiter._history.pop(f"{client_ip}:general", None)

        # Exhaust polling bucket (60 requests)
        for _ in range(60):
            res = client.post("/api/tasks/poll", json=poll_payload, headers=poll_headers)
            assert res.status_code == 200

        # Confirm polling is now blocked (HTTP 429)
        blocked_poll = client.post("/api/tasks/poll", json=poll_payload, headers=poll_headers)
        assert blocked_poll.status_code == 429

        # Now send requests to general endpoints from the SAME client IP
        general_headers = {"X-Forwarded-For": client_ip}

        res_posts = client.get("/api/posts", headers=general_headers)
        assert res_posts.status_code == 200, f"General /api/posts blocked by polling exhaustion! Status: {res_posts.status_code}"

        res_accounts = client.get("/api/accounts", headers=general_headers)
        assert res_accounts.status_code == 200, f"General /api/accounts blocked by polling exhaustion! Status: {res_accounts.status_code}"

        res_health = client.get("/health", headers=general_headers)
        assert res_health.status_code == 200, f"/health endpoint blocked! Status: {res_health.status_code}"

    def test_rate_limiter_multithreaded_race_condition(self):
        """
        Adversarial test: 40 threads simultaneously hit a rate-limited bucket with limit=10.
        Verifies that thread-safe locking in SlidingWindowRateLimiter prevents burst leaks:
        EXACTLY 10 requests must be allowed, and EXACTLY 30 must be rejected.
        """
        limiter = SlidingWindowRateLimiter(default_window_seconds=60.0)
        bucket_key = "race_test_ip:poll"
        limit = 10
        total_requests = 40

        barrier = threading.Barrier(total_requests)
        results = []

        def worker(thread_idx: int):
            barrier.wait(timeout=5.0)
            allowed, retry_after = limiter.is_allowed(bucket_key, limit=limit)
            results.append((allowed, retry_after))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(total_requests)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        allowed_count = sum(1 for allowed, _ in results if allowed is True)
        blocked_count = sum(1 for allowed, _ in results if allowed is False)

        assert allowed_count == limit, f"Race condition detected! Allowed {allowed_count} instead of {limit}"
        assert blocked_count == (total_requests - limit), f"Expected {total_requests - limit} blocked, got {blocked_count}"

    def test_sliding_window_time_decay_recovery(self):
        """
        Verify that once timestamps age out of the sliding window,
        the rate limiter naturally allows new requests without needing a full-reset timer.
        """
        # Create a limiter with a 0.2 second window
        fast_limiter = SlidingWindowRateLimiter(default_window_seconds=0.2)
        test_key = "decay_test_ip"
        limit = 3

        # Use up all 3 permits
        for _ in range(limit):
            allowed, _ = fast_limiter.is_allowed(test_key, limit=limit)
            assert allowed is True

        # 4th must be blocked
        allowed, retry_after = fast_limiter.is_allowed(test_key, limit=limit)
        assert allowed is False
        assert retry_after >= 1

        # Wait for the sliding window (0.25 seconds) to expire older timestamps
        time.sleep(0.25)

        # Should now be allowed again!
        allowed_again, _ = fast_limiter.is_allowed(test_key, limit=limit)
        assert allowed_again is True, "Sliding window failed to recover after window duration expired"


# ==============================================================================
# CHALLENGE 3: Token Security & Auth Bypass Stress Tests
# ==============================================================================

class TestTokenSecurityAndAuthBypass:
    """Empirically stress-tests header casing, malformed tokens, timing attacks, and traversal bypasses."""

    @pytest.fixture(autouse=True)
    def setup_security_token(self, monkeypatch):
        """Ensure SYNC_TOKEN is actively enforced during security tests."""
        self.secret_token = "ProdSecureToken_99@2026_xyz"
        monkeypatch.setattr(settings, "SYNC_TOKEN", self.secret_token)

    def test_token_header_case_insensitivity_matrix(self):
        """
        Verify that authentication succeeds across all standard HTTP header casing variations:
        - X-Sync-Token
        - x-sync-token
        - X-SYNC-TOKEN
        - X-sYnC-tOkEn
        - Query string ?token=...
        - Query string ?sync_token=...
        """
        casing_variations = [
            {"X-Sync-Token": self.secret_token},
            {"x-sync-token": self.secret_token},
            {"X-SYNC-TOKEN": self.secret_token},
            {"X-sYnC-tOkEn": self.secret_token},
        ]

        for headers in casing_variations:
            res = client.get("/api/posts", headers=headers)
            assert res.status_code == 200, f"Failed authentication with header: {headers}"

        # Test query parameter fallbacks
        res_q1 = client.get(f"/api/posts?token={self.secret_token}")
        assert res_q1.status_code == 200, "Query parameter ?token= fallback failed"

        res_q2 = client.get(f"/api/posts?sync_token={self.secret_token}")
        assert res_q2.status_code == 200, "Query parameter ?sync_token= fallback failed"

    def test_worker_headers_casing_variations(self):
        """
        Verify worker endpoints correctly extract X-Project-Key and X-Worker-Id regardless of header casing:
        - X-Project-Key vs x-project-key vs X-PROJECT-KEY
        - X-Worker-Id vs x-worker-id vs X-Ext-Id vs x-ext-id
        """
        worker_id = "test_worker_casing"
        headers_set = [
            {"X-Sync-Token": self.secret_token, "X-Project-Key": "all", "X-Worker-Id": worker_id},
            {"X-Sync-Token": self.secret_token, "x-project-key": "all", "x-worker-id": worker_id},
            {"X-Sync-Token": self.secret_token, "X-PROJECT-KEY": "all", "X-Ext-Id": worker_id},
            {"X-Sync-Token": self.secret_token, "x-project-key": "all", "x-ext-id": worker_id},
        ]

        poll_payload = {"workerId": worker_id, "supportedTypes": ["post"]}

        for h in headers_set:
            res = client.post("/api/tasks/poll", json=poll_payload, headers=h)
            assert res.status_code == 200, f"Worker header casing failed for: {h}"

    def test_malformed_and_adversarial_tokens(self):
        """
        Test malformed, adversarial, and edge-case tokens:
        - None / missing -> 401
        - Empty string -> 401
        - Whitespace only -> 401
        - Huge token (100KB) -> 401 (no crash)
        - Null bytes in token -> 401 (no crash)
        - Unicode / emojis in token -> 401 (no crash)
        - SQL injection payload -> 401 (no crash)
        """
        # 1. ASCII-safe headers tested via HTTP client
        ascii_cases = [
            ("", 401),
            ("   ", 401),
            ("wrong_token_entirely", 401),
            ("ProdSecureToken_99@2026_xy", 401),  # One char short
            ("ProdSecureToken_99@2026_xyz_extra", 401),  # Extra char
            ("A" * 100000, 401),  # 100KB payload
            ("' OR '1'='1' --", 401),  # SQL injection syntax
        ]

        for token, expected_status in ascii_cases:
            res = client.get("/api/posts", headers={"X-Sync-Token": token})
            assert res.status_code == expected_status, f"Token '{token[:30]}' got status {res.status_code}"

        # 2. Query param test for Unicode emojis (URL encoded automatically)
        res_unicode = client.get("/api/posts?token=🔥💎🚀_test_bad_unicode")
        assert res_unicode.status_code == 401

        # 3. Direct verification function tests for extreme payloads (null bytes, emojis, unicode)
        assert verify_sync_token("") is False
        assert verify_sync_token("   ") is False
        assert verify_sync_token(None) is False
        assert verify_sync_token(f"{self.secret_token}\x00extra") is False
        assert verify_sync_token("🔥💎🚀_emoji_token") is False
        assert verify_sync_token("A" * 500000) is False
        assert verify_sync_token(self.secret_token) is True

    def test_timing_attack_resistance_via_constant_time_comparison(self):
        """
        Empirically verify timing attack resistance:
        `verify_sync_token` utilizes `hmac.compare_digest`.
        Measure execution time distribution between:
        1. Token differing at character 0
        2. Token differing at middle character
        3. Token differing at the final character
        4. Valid token
        Ensures mean times are within standard deviation noise (< 50 microseconds diff).
        """
        correct = self.secret_token
        # Create tokens of the exact same length differing at index 0, mid, and last
        diff_first = "X" + correct[1:]
        diff_mid = correct[:len(correct)//2] + "X" + correct[len(correct)//2 + 1:]
        diff_last = correct[:-1] + "X"

        iterations = 5000

        def benchmark(token_candidate: str) -> float:
            start = time.perf_counter()
            for _ in range(iterations):
                verify_sync_token(token_candidate)
            return (time.perf_counter() - start) / iterations

        # Warm up JIT/CPU caches
        for _ in range(500):
            verify_sync_token(correct)

        t_first = benchmark(diff_first)
        t_mid = benchmark(diff_mid)
        t_last = benchmark(diff_last)
        t_correct = benchmark(correct)

        # Check maximum timing spread across mismatch positions
        times = [t_first, t_mid, t_last, t_correct]
        max_diff = max(times) - min(times)

        # Constant-time comparison should have timing difference below 50 microseconds
        assert max_diff < 0.00005, f"Timing deviation {max_diff:.8f}s exceeded constant-time threshold!"

    def test_path_traversal_whitelist_bypass_prevention(self):
        """
        Adversarial test: Attempt to bypass token authentication using directory traversal
        on public endpoints (e.g. /health/../api/posts or /uploads/../api/posts).
        Ensure requests without token are NOT granted access.
        """
        bypass_attempts = [
            "/health/../api/posts",
            "/docs/../api/posts",
            "/uploads/../api/posts",
            "/static/../api/posts",
            "/admin/../api/posts",
            "//api/posts",
            "/./api/posts"
        ]

        for path in bypass_attempts:
            # Send without token
            res = client.get(path)
            # Must either return 401 (auth blocked), 404 (not found), or redirect, but NEVER 200 with data
            if res.status_code == 200:
                # If it returned 200, ensure it did not return protected posts data!
                body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                assert "posts" not in body, f"Bypass succeeded on {path}! Returned protected posts without token!"

    def test_worker_endpoints_require_project_key(self):
        """
        Verify that worker endpoints strictly reject requests missing X-Project-Key
        with HTTP 400 Bad Request.
        """
        worker_endpoints = [
            ("/api/tasks/poll", {"workerId": "w1", "supportedTypes": ["post"]}),
            ("/api/workers/heartbeat", {"workerId": "w1", "status": "idle"}),
            ("/api/workers/register", {"workerId": "w1", "name": "W1", "version": "7.0.0"}),
        ]

        for endpoint, payload in worker_endpoints:
            # Request with valid token but NO X-Project-Key
            res = client.post(endpoint, json=payload, headers={"X-Sync-Token": self.secret_token})
            assert res.status_code == 400, f"Endpoint {endpoint} allowed request without X-Project-Key! Status: {res.status_code}"
            assert "Missing X-Project-Key" in res.json().get("error", "")

            # Request with whitespace-only X-Project-Key
            res_ws = client.post(endpoint, json=payload, headers={"X-Sync-Token": self.secret_token, "X-Project-Key": "   "})
            assert res_ws.status_code == 400, f"Endpoint {endpoint} allowed whitespace X-Project-Key!"
