"""
fbauto-backend-python/tests/test_challenger_m1_2.py
Milestone 1 Adversarial & Empirical Test Suite by Challenger 2.

Covers:
1. Media Offloading (large images, corrupted base64, path traversal, extension mapping, zero-byte leak)
2. Database Deduplication (repeated sequential POST /api/accounts, concurrent insertion race condition, targets sync)
3. Docker Compose & VPS Configuration (YAML validity, variable substitution, volume bindings, healthcheck)
"""

import os
import sys
import json
import base64
import hashlib
import subprocess
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.core.config import settings
from app.services.media_service import save_base64_media, sanitize_filename
from app.db.session import query_all, query_one, execute_write

# Default test client
client = TestClient(app)
# Resilient test client that captures HTTP 500 instead of raising in test thread
resilient_client = TestClient(app, raise_server_exceptions=False)

# ==============================================================================
# SECTION 1: MEDIA OFFLOADING & CORRUPTED PAYLOAD TESTS
# ==============================================================================

class TestMediaOffloading:
    """Empirical tests for media offloading, large payloads, and corrupted base64 handling."""

    def test_media_large_payload_5mb(self):
        """Upload a 5MB binary payload to test memory safety and byte-level disk fidelity."""
        # Generate 5 MB of pseudo-random bytes with distinct header/footer
        size_5mb = 5 * 1024 * 1024
        raw_binary = b"START_OF_5MB_TEST_" + os.urandom(size_5mb - 36) + b"_END_OF_5MB_TEST"
        expected_sha256 = hashlib.sha256(raw_binary).hexdigest()
        b64_str = base64.b64encode(raw_binary).decode("utf-8")

        post_payload = {
            "content": "Challenger 2 Large 5MB Media Test Post",
            "postType": "post",
            "targetType": "profile",
            "targetId": "challenger_target_large_media",
            "mediaData": {
                "base64": b64_str,
                "fileName": "large_test_payload.png",
                "mimeType": "image/png"
            }
        }

        res = client.post("/api/posts", json=post_payload)
        assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["success"] is True
        post = data["post"]
        media_path = post["mediaPath"]
        media_url = post["mediaUrl"]

        # 1. Verify file on disk
        full_disk_path = os.path.join(settings.BASE_DIR, media_path)
        assert os.path.exists(full_disk_path), f"File {full_disk_path} does not exist on disk"
        with open(full_disk_path, "rb") as f:
            disk_bytes = f.read()
        assert len(disk_bytes) == len(raw_binary), f"Size mismatch: {len(disk_bytes)} != {len(raw_binary)}"
        disk_sha256 = hashlib.sha256(disk_bytes).hexdigest()
        assert disk_sha256 == expected_sha256, "Disk file SHA256 does not match original binary!"

        # 2. Verify static serving endpoint via GET /uploads/...
        get_res = client.get(media_url)
        assert get_res.status_code == 200
        assert len(get_res.content) == len(raw_binary)
        assert hashlib.sha256(get_res.content).hexdigest() == expected_sha256

        # Cleanup test file and post record
        try:
            os.remove(full_disk_path)
        except OSError:
            pass
        execute_write("DELETE FROM posts WHERE id = ?", (post["id"],))

    def test_corrupted_base64_direct_service(self):
        """Test save_base64_media service directly against corrupted and malformed payloads."""
        corrupted_cases = [
            ("garbage_chars", "!!!NOT_A_VALID_BASE64_STRING_AT_ALL???###"),
            ("truncated_bad_padding", "YWJjZGVmZw"),  # 10 chars, missing padding
            ("invalid_data_uri_no_comma", "data:image/png;base64"),
            ("corrupted_data_uri_body", "data:image/png;base64,%%%%CORRUPT%%%%"),
            ("empty_string", ""),
            ("none_payload", None),
        ]

        for label, bad_b64 in corrupted_cases:
            payload = {"base64": bad_b64, "fileName": f"corrupt_{label}.png"} if bad_b64 is not None else None
            url, path = save_base64_media(payload, f"test_corrupt_{label}")
            assert url is None, f"Expected None for corrupted case '{label}', got url: {url}"
            assert path is None, f"Expected None for corrupted case '{label}', got path: {path}"

    def test_whitespace_base64_zero_byte_behavior(self):
        """
        Adversarial Observation: When base64 payload is whitespace-only,
        base64.b64decode returns b'' and writes a 0-byte file to disk.
        Documents and verifies the vulnerability behavior.
        """
        payload = {"base64": "    ", "fileName": "whitespace_leak.png", "mimeType": "image/png"}
        url, path = save_base64_media(payload, "test_ws_leak")
        if url is not None:
            # File was created with 0 bytes
            full_path = os.path.join(settings.BASE_DIR, path)
            file_exists = os.path.exists(full_path)
            file_size = os.path.getsize(full_path) if file_exists else -1
            try:
                os.remove(full_path)
            except OSError:
                pass
            assert file_size == 0, f"Expected 0 bytes, got {file_size}"

    def test_corrupted_base64_post_creation_fallback(self):
        """When post has content and corrupted base64 media, verify it falls back gracefully without 500 error."""
        post_payload = {
            "content": "Post with corrupted media payload",
            "postType": "post",
            "targetType": "profile",
            "mediaData": {
                "base64": "~~~CORRUPT_BASE64_BYTES~~~",
                "fileName": "corrupted.png",
                "mimeType": "image/png"
            }
        }

        res = client.post("/api/posts", json=post_payload)
        # Should not crash with 500 Internal Server Error
        assert res.status_code == 201, f"Expected graceful 201, got {res.status_code}: {res.text}"
        post = res.json()["post"]
        # mediaUrl and mediaPath should be empty string
        assert post["mediaUrl"] == ""
        assert post["mediaPath"] == ""
        # Clean up
        execute_write("DELETE FROM posts WHERE id = ?", (post["id"],))

    def test_empty_content_with_corrupted_base64(self):
        """
        Adversarial Edge Case: Content is empty, and mediaData is corrupted base64.
        Validates whether system inserts an empty ghost post.
        """
        post_payload = {
            "content": "",
            "postType": "post",
            "targetType": "profile",
            "mediaData": {
                "base64": "!!!INVALID_BASE64_ONLY!!!",
                "fileName": "ghost.png",
                "mimeType": "image/png"
            }
        }
        res = client.post("/api/posts", json=post_payload)
        # Empirically verify that line 124 passes because mediaData is non-empty dict,
        # but media decoding fails, resulting in an empty ghost post.
        if res.status_code == 201:
            post = res.json()["post"]
            assert post["content"] == ""
            assert post["mediaUrl"] == ""
            # Clean up the ghost post from DB
            execute_write("DELETE FROM posts WHERE id = ?", (post["id"],))

    def test_path_traversal_and_filename_sanitization(self):
        """Test malicious filenames with directory traversal tokens and special characters."""
        traversal_filenames = [
            "../../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\cmd.exe",
            "test/../../../uploads/hacked.sh",
            "con.txt",
            "very_long_" + "a" * 200 + ".png",
            "filename with spaces and #@! symbols.jpg",
            ".hidden_file.png",
        ]

        sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b64_str = base64.b64encode(sample_png).decode("utf-8")

        for idx, malicious_name in enumerate(traversal_filenames):
            entity_id = f"sec_test_{idx}"
            media_data = {
                "base64": b64_str,
                "fileName": malicious_name,
                "mimeType": "image/png"
            }
            url, path = save_base64_media(media_data, entity_id)
            assert url is not None, f"Failed to save sanitized file for {malicious_name}"

            # Verify resolved path is strictly inside settings.UPLOADS_DIR
            resolved_full = os.path.abspath(os.path.join(settings.BASE_DIR, path))
            uploads_dir_full = os.path.abspath(settings.UPLOADS_DIR)
            assert resolved_full.startswith(uploads_dir_full), (
                f"Path traversal escape detected! '{resolved_full}' is outside '{uploads_dir_full}'"
            )
            # Cleanup
            if os.path.exists(resolved_full):
                try:
                    os.remove(resolved_full)
                except OSError:
                    pass


# ==============================================================================
# SECTION 2: DATABASE DEDUPLICATION & CONCURRENCY TESTS
# ==============================================================================

class TestDatabaseDeduplication:
    """Empirical tests for account deduplication, sequential repetitions, and concurrent race conditions."""

    def test_repeated_sequential_account_upserts(self):
        """
        Verify that repeating POST /api/accounts with identical targetId:
        1. Maintains exactly 1 DB record (zero duplicates).
        2. Updates name, accessToken, and updated_at.
        3. Preserves original id and created_at.
        """
        target_id = f"dedup_target_seq_{int(os.getpid())}_{hashlib.md5(os.urandom(4)).hexdigest()[:6]}"

        # Step 1: Initial creation
        initial_payload = {
            "name": "Sequential Account V1",
            "accessToken": "EAAB_token_v1",
            "targetId": target_id,
            "type": "profile",
            "projectKey": "alpha"
        }
        res1 = client.post("/api/accounts", json=initial_payload)
        assert res1.status_code == 201
        acc1 = res1.json()["account"]
        orig_id = acc1["id"]
        orig_created_at = acc1["createdAt"]

        # Step 2: Repeat 10 times with modified fields
        for i in range(2, 12):
            update_payload = {
                "name": f"Sequential Account V{i}",
                "accessToken": f"EAAB_token_v{i}",
                "targetId": target_id,
                "type": "page" if i % 2 == 0 else "group",
                "projectKey": "beta"
            }
            res = client.post("/api/accounts", json=update_payload)
            assert res.status_code == 201, f"Iteration {i} failed: {res.text}"
            acc = res.json()["account"]
            assert acc["id"] == orig_id, f"Account ID mutated on iteration {i}!"
            assert acc["createdAt"] == orig_created_at, f"createdAt mutated on iteration {i}!"
            assert acc["name"] == f"Sequential Account V{i}"
            assert acc["accessToken"] == f"EAAB_token_v{i}"

        # Step 3: Check database count for this target_id
        db_rows = query_all("SELECT * FROM accounts WHERE target_id = ?", (target_id,))
        assert len(db_rows) == 1, f"Deduplication failed! Expected 1 row, found {len(db_rows)}"
        assert db_rows[0]["name"] == "Sequential Account V11"

        # Cleanup
        execute_write("DELETE FROM accounts WHERE target_id = ?", (target_id,))

    def test_concurrent_account_creation_race_condition(self):
        """
        Stress test: 10 concurrent threads attempt to create an account with the identical new targetId simultaneously.
        Verifies:
        1. Zero duplicate rows in database (data integrity guarantee: COUNT == 1).
        2. Measures whether check-then-act race condition results in 500 errors.
        """
        concurrent_target = f"race_target_{int(os.getpid())}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"
        thread_count = 10
        results = []

        def worker_post(idx):
            payload = {
                "name": f"Race Account Worker {idx}",
                "accessToken": f"EAAB_race_token_{idx}",
                "targetId": concurrent_target,
                "type": "profile",
                "projectKey": "all"
            }
            # Use resilient_client to capture 500 rather than crashing test runner
            r = resilient_client.post("/api/accounts", json=payload)
            return r.status_code, r.text

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(worker_post, i) for i in range(thread_count)]
            for fut in as_completed(futures):
                results.append(fut.result())

        # CRITICAL TEST: Check database state: How many rows were inserted?
        rows = query_all("SELECT * FROM accounts WHERE target_id = ?", (concurrent_target,))
        assert len(rows) == 1, (
            f"CRITICAL DATA INTEGRITY FAILURE: Duplicate accounts created! Count: {len(rows)}"
        )

        status_codes = [code for code, _ in results]
        print(f"\n[CONCURRENCY RACE TEST] Status codes received: {status_codes}")
        # Note: If 500 errors appear, it empirically proves the check-then-act race condition
        # (while database integrity is preserved by UNIQUE constraint).

        # Cleanup
        execute_write("DELETE FROM accounts WHERE target_id = ?", (concurrent_target,))

    def test_target_sync_deduplication(self):
        """Verify POST /api/accounts/targets deduplicates repeated targets via INSERT OR REPLACE."""
        target_id = f"discovered_fanpage_{int(os.getpid())}"
        sync_payload = {
            "targets": [
                {"id": target_id, "name": "Fanpage V1", "type": "page"},
                {"id": target_id, "name": "Fanpage V2", "type": "page"},
                {"id": f"group_{int(os.getpid())}", "name": "Group A", "type": "group"}
            ]
        }

        res = client.post("/api/accounts/targets", json=sync_payload)
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Check targets table
        rows = query_all("SELECT * FROM targets WHERE id = ?", (target_id,))
        assert len(rows) == 1, f"Expected 1 target row, got {len(rows)}"
        assert rows[0]["name"] == "Fanpage V2"

        # Cleanup
        execute_write("DELETE FROM targets WHERE id IN (?, ?)", (target_id, f"group_{int(os.getpid())}"))


# ==============================================================================
# SECTION 3: DOCKER COMPOSE & VPS ENVIRONMENT VALIDATION
# ==============================================================================

class TestDockerComposeAndVPSReadiness:
    """Empirical verification of docker-compose.yml, environment variable substitution, and Dockerfile."""

    def test_docker_compose_config_default(self):
        """Verify docker compose config runs without errors and outputs valid yaml with defaults."""
        root_dir = os.path.dirname(BACKEND_DIR)
        res = subprocess.run(
            ["docker", "compose", "config"],
            cwd=root_dir,
            capture_output=True,
            text=True
        )
        assert res.returncode == 0, f"docker compose config failed: {res.stderr}"
        assert "fbauto-backend" in res.stdout
        assert "fbauto-backend-prod" in res.stdout
        assert "19823" in res.stdout
        assert "fbauto_secret_token_prod_2026" in res.stdout

    def test_docker_compose_environment_substitutions(self):
        """Verify docker compose config honors custom environment variable overrides."""
        root_dir = os.path.dirname(BACKEND_DIR)
        custom_env = os.environ.copy()
        custom_env["PORT"] = "29823"
        custom_env["SYNC_TOKEN"] = "adversarial_custom_secret_key_999"
        custom_env["PROJECT_KEY_DEFAULT"] = "team_alpha"
        custom_env["RATE_LIMIT_POLL_PER_MIN"] = "90"
        custom_env["RATE_LIMIT_ENABLED"] = "false"

        res = subprocess.run(
            ["docker", "compose", "config"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            env=custom_env
        )
        assert res.returncode == 0, f"docker compose config failed: {res.stderr}"
        config_text = res.stdout

        # Verify variable substitutions in output YAML
        assert "29823" in config_text, "PORT override not reflected in docker compose config!"
        assert "adversarial_custom_secret_key_999" in config_text, "SYNC_TOKEN override not reflected!"
        assert "team_alpha" in config_text, "PROJECT_KEY_DEFAULT override not reflected!"
        assert "90" in config_text, "RATE_LIMIT_POLL_PER_MIN override not reflected!"

    def test_docker_compose_volume_bindings(self):
        """Verify docker compose config maps persistent SQLite, uploads, and logs volumes."""
        root_dir = os.path.dirname(BACKEND_DIR)
        res = subprocess.run(
            ["docker", "compose", "config"],
            cwd=root_dir,
            capture_output=True,
            text=True
        )
        assert res.returncode == 0
        stdout = res.stdout

        # Verify volume target paths inside container
        assert "/app/data" in stdout, "Missing /app/data volume bind!"
        assert "/app/uploads" in stdout, "Missing /app/uploads volume bind!"
        assert "/app/logs" in stdout, "Missing /app/logs volume bind!"

    def test_dockerfile_security_and_non_root(self):
        """Inspect Dockerfile for security hardening and non-root execution."""
        dockerfile_path = os.path.join(BACKEND_DIR, "Dockerfile")
        assert os.path.exists(dockerfile_path), "Dockerfile not found!"

        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "FROM python:3.11-slim" in content, "Should use python:3.11-slim"
        assert "useradd" in content or "adduser" in content, "Should create dedicated non-root user"
        assert "USER appuser" in content, "Must switch to non-root USER before entrypoint"
        assert "HEALTHCHECK" in content, "Must declare HEALTHCHECK instruction"
        assert "uvicorn" in content, "CMD must execute uvicorn production server"
