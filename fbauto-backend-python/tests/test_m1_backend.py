"""
Unit and integration tests for Milestone 1 Backend Modernization, Security, and SQLite WAL.
"""

import os
import sys
import json
import base64
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app.core.config import settings
from app.core.rate_limiter import rate_limiter

client = TestClient(app)

def test_health_endpoint():
    """Verify /health returns 200 and healthy status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["engine"] == "FastAPI"

def test_sync_status():
    """Verify /sync/status probe returns version 7.0.0."""
    res = client.get("/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["version"] == "7.0.0"

def test_admin_console_html():
    """Verify / serves admin.html with no-cache headers."""
    res = client.get("/")
    assert res.status_code == 200
    assert "no-cache" in res.headers.get("cache-control", "")

def test_list_posts():
    """Verify /api/posts returns list and total count."""
    res = client.get("/api/posts")
    assert res.status_code == 200
    data = res.json()
    assert "posts" in data
    assert "total" in data
    assert isinstance(data["posts"], list)
    assert data["total"] >= 1

def test_create_post_with_media_offloading():
    """Verify creating a post with Base64 media extracts it into uploads/ and saves relative URL."""
    sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    b64_str = base64.b64encode(sample_png).decode("utf-8")

    payload = {
        "content": "Test media post with offloading",
        "postType": "post",
        "targetType": "page",
        "targetId": "123456789",
        "mediaData": {
            "base64": b64_str,
            "fileName": "test_graphic.png",
            "mimeType": "image/png"
        },
        "seedingComments": ["Nice post!", "Super informative!"]
    }

    res = client.post("/api/posts", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    post = data["post"]
    assert post["content"] == payload["content"]
    assert post["mediaUrl"].startswith("/uploads/")
    assert post["mediaPath"].startswith("uploads/")
    assert len(post["seedingComments"]) == 2

    # Check physical file on disk
    file_path = os.path.join(settings.BASE_DIR, post["mediaPath"])
    assert os.path.exists(file_path)
    with open(file_path, "rb") as f:
        saved_bytes = f.read()
    assert saved_bytes == sample_png

    # Check static file GET /uploads/...
    media_res = client.get(post["mediaUrl"])
    assert media_res.status_code == 200
    assert media_res.content == sample_png

def test_accounts_deduplication():
    """Verify accounts are listed and deduplication works on upsert."""
    res = client.get("/api/accounts")
    assert res.status_code == 200
    data = res.json()
    assert "accounts" in data
    initial_count = data["total"]

    # Upsert an account with an existing targetId
    unique_target = "test_target_dedup_99"
    payload1 = {
        "name": "Original Name",
        "accessToken": "token_v1",
        "targetId": unique_target,
        "type": "profile"
    }
    r1 = client.post("/api/accounts", json=payload1)
    assert r1.status_code in [200, 201]

    # Re-post with updated name and token for same targetId
    payload2 = {
        "name": "Updated Name",
        "accessToken": "token_v2",
        "targetId": unique_target,
        "type": "page"
    }
    r2 = client.post("/api/accounts", json=payload2)
    assert r2.status_code in [200, 201]
    acc = r2.json()["account"]
    assert acc["name"] == "Updated Name"
    assert acc["accessToken"] == "token_v2"
    assert acc["type"] == "page"

    # Verify no duplicate was added
    r_list = client.get("/api/accounts")
    matching = [a for a in r_list.json()["accounts"] if a["targetId"] == unique_target]
    assert len(matching) == 1

def test_projects_crud():
    """Verify projects CRUD endpoints."""
    # List
    r_list = client.get("/api/projects")
    assert r_list.status_code == 200

    # Create/Upsert
    payload = {
        "id": "test_project_alpha",
        "name": "Test Project Alpha",
        "description": "Integration test project"
    }
    r_create = client.post("/api/projects", json=payload)
    assert r_create.status_code == 200
    assert r_create.json()["success"] is True

    # Delete
    r_del = client.delete("/api/projects/test_project_alpha")
    assert r_del.status_code == 200
    assert r_del.json()["success"] is True

def test_settings_get_and_update():
    """Verify /api/settings retrieves and updates cfg_main."""
    r_get = client.get("/api/settings")
    assert r_get.status_code == 200
    settings_data = r_get.json()["settings"]
    assert settings_data["id"] == "cfg_main"

    updated_payload = dict(settings_data)
    updated_payload["seedingMinDelay"] = 5
    r_post = client.post("/api/settings", json=updated_payload)
    assert r_post.status_code == 200
    assert r_post.json()["settings"]["seedingMinDelay"] == 5

def test_ai_suggest_reply():
    """Verify /api/ai/suggest-reply generates tone-appropriate reply."""
    payload = {
        "commentText": "Báo giá cho mình với shop",
        "tone": "sales"
    }
    res = client.post("/api/ai/suggest-reply", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "inbox" in data["suggestedReply"].lower() or "giá" in data["suggestedReply"].lower()

def test_worker_register_and_heartbeat():
    """Verify worker node registration and heartbeat with X-Project-Key and X-Worker-Id headers."""
    worker_id = "node_pytest_test_worker_01"
    headers = {
        "X-Project-Key": "all",
        "X-Worker-Id": worker_id
    }
    reg_payload = {
        "workerId": worker_id,
        "name": "Pytest Node",
        "projectKey": "all",
        "version": "7.0.0",
        "assignedAccounts": ["target_1", "target_2"]
    }

    # Verify 400 if missing X-Project-Key
    r_bad = client.post("/api/workers/register", json=reg_payload)
    assert r_bad.status_code == 400
    assert "Missing X-Project-Key" in r_bad.json()["error"]

    # Valid registration with headers
    r_reg = client.post("/api/workers/register", json=reg_payload, headers=headers)
    assert r_reg.status_code == 200
    assert r_reg.json()["status"] == "ok"
    assert r_reg.json()["workerId"] == worker_id

    hb_payload = {
        "workerId": worker_id,
        "status": "idle"
    }
    r_hb = client.post("/api/workers/heartbeat", json=hb_payload, headers=headers)
    assert r_hb.status_code == 200
    assert r_hb.json()["status"] == "ok"

    # List workers
    r_workers = client.get("/api/workers")
    assert r_workers.status_code == 200
    matching = [w for w in r_workers.json()["workers"] if w["id"] == worker_id]
    assert len(matching) == 1

def test_task_queue_poll_and_lease():
    """Verify creating a task, atomic poll claiming with 60s lease, and status reporting."""
    worker_id = "node_pytest_worker_claimer"
    headers = {
        "X-Project-Key": "all",
        "X-Worker-Id": worker_id
    }

    # Create task assigned to this worker with highest priority
    task_payload = {
        "taskType": "warmup",
        "projectKey": "all",
        "workerId": worker_id,
        "priority": 999999999,
        "payload": {"durationSeconds": 120}
    }
    r_task = client.post("/api/tasks", json=task_payload)
    assert r_task.status_code == 201
    created_task = r_task.json()["task"]
    task_id = created_task["id"]

    # Worker claims task
    poll_payload = {
        "workerId": worker_id,
        "supportedTypes": ["warmup", "post"]
    }

    # Verify 400 if missing X-Project-Key
    r_bad_poll = client.post("/api/tasks/poll", json=poll_payload)
    assert r_bad_poll.status_code == 400

    # Valid poll with headers
    r_poll = client.post("/api/tasks/poll", json=poll_payload, headers=headers)
    assert r_poll.status_code == 200
    claimed = r_poll.json()["task"]
    assert claimed is not None
    assert claimed["id"] == task_id
    assert claimed["status"] == "assigned"
    assert claimed["workerId"] == worker_id
    assert claimed["leaseExpiresAt"] > claimed["claimedAt"]

    # Worker reports completion
    status_payload = {
        "workerId": worker_id,
        "status": "completed",
        "result": {"scrolledPages": 10, "reactionsGiven": 3}
    }
    r_status = client.post(f"/api/tasks/{task_id}/status", json=status_payload, headers=headers)
    assert r_status.status_code == 200
    assert r_status.json()["status"] == "ok"

def test_security_sync_token_enforcement(monkeypatch):
    """Verify that when SYNC_TOKEN is enabled, requests without token or with invalid token get 401."""
    monkeypatch.setattr(settings, "SYNC_TOKEN", "super_secret_test_token")

    # Request without token to protected endpoint
    res_no_token = client.get("/api/posts")
    assert res_no_token.status_code == 401
    assert "Unauthorized" in res_no_token.json()["error"]

    # Request with invalid token
    res_bad_token = client.get("/api/posts", headers={"X-Sync-Token": "wrong_token"})
    assert res_bad_token.status_code == 401

    # Request with valid token
    res_good_token = client.get("/api/posts", headers={"X-Sync-Token": "super_secret_test_token"})
    assert res_good_token.status_code == 200

    # Public endpoint remains accessible without token
    res_health = client.get("/health")
    assert res_health.status_code == 200

def test_rate_limiter_threshold():
    """Verify sliding-window rate limiter blocks requests exceeding configured limit."""
    # Test rate limiter directly
    client_key = "test_ip_rate_limit:poll"
    limit = 5

    # Reset/clear bucket
    with rate_limiter._lock:
        if client_key in rate_limiter._history:
            del rate_limiter._history[client_key]

    for i in range(limit):
        allowed, retry_after = rate_limiter.is_allowed(client_key, limit=limit)
        assert allowed is True
        assert retry_after == 0

    # Next request should be blocked
    allowed, retry_after = rate_limiter.is_allowed(client_key, limit=limit)
    assert allowed is False
    assert retry_after > 0
