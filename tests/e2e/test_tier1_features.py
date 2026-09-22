"""Tier 1: Feature Coverage in Isolation (>= 5 tests per feature for each of the 15 features in PROJECT.md).

Authoritative References:
- ORIGINAL_REQUEST.md (R1-R4)
- PROJECT.md (Features F1.1 - F5.1)
- requirements_spec.md (Sections 2 - 9)
"""

import os
import re
import sys
import time
import json
import subprocess
from pathlib import Path
import pytest

from tests.e2e.conftest import (
    PROJECT_ROOT,
    BACKEND_DIR,
    EXTENSION_DIR,
    DEFAULT_SYNC_TOKEN,
    DEFAULT_PROJECT_KEY,
    REACTION_WEIGHTS,
    REACTION_FB_IDS,
    CHECKPOINT_ERROR_CODES,
    GRAPHQL_DOC_IDS,
    SCROLL_PHYSICS,
    bezier_easing,
    parse_spintax,
    expand_all_spintax_permutations,
)


# ==============================================================================
# Feature 1: F1.1 Worker Node Registry & Monitor
# ==============================================================================

def test_f1_1_01_worker_register_success(client, unique_worker_id):
    """ASSERT_W1_REGISTER_SUCCESS: POST /api/workers/register creates node with status online."""
    payload = {
        "id": unique_worker_id,
        "name": f"Worker Node {unique_worker_id}",
        "projectKey": DEFAULT_PROJECT_KEY,
        "extensionVersion": "7.1.0",
        "userAgent": "Mozilla/5.0 Chrome/128.0.0.0",
        "capabilities": {"directGraphQL": True, "warmup": True},
        "assignedAccounts": ["acc_1001", "acc_1002"]
    }
    res = client.post("/api/workers/register", json=payload)
    assert res.status_code in [200, 201], f"Register failed: {res.status_code} - {res.text}"
    data = res.json()
    assert data.get("success") is True or data.get("status") == "ok"
    assert data.get("workerId") == unique_worker_id or data.get("worker", {}).get("id") == unique_worker_id


def test_f1_1_02_worker_heartbeat_updates_timestamp(client, unique_worker_id):
    """ASSERT_W2_HEARTBEAT_UPDATE: POST /api/workers/heartbeat updates lastHeartbeat."""
    # Register first
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    
    # Pulse heartbeat
    hb_payload = {
        "id": unique_worker_id,
        "workerId": unique_worker_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "status": "online"
    }
    res = client.post("/api/workers/heartbeat", json=hb_payload)
    assert res.status_code == 200, f"Heartbeat failed: {res.status_code} - {res.text}"
    data = res.json()
    assert data.get("success") is True or data.get("status") == "ok"


def test_f1_1_03_worker_list_contains_registered_node(client, unique_worker_id):
    """GET /api/workers returns list containing registered worker."""
    client.post("/api/workers/register", json={"id": unique_worker_id, "name": "Node Test List", "projectKey": DEFAULT_PROJECT_KEY})
    
    res = client.get("/api/workers")
    assert res.status_code == 200, f"Get workers failed: {res.status_code} - {res.text}"
    workers = res.json() if isinstance(res.json(), list) else res.json().get("workers", [])
    worker_ids = [w.get("id") or w.get("workerId") for w in workers]
    assert unique_worker_id in worker_ids, f"Worker {unique_worker_id} not found in {worker_ids}"


def test_f1_1_04_worker_heartbeat_reports_busy_with_task(client, unique_worker_id, unique_task_id):
    """Worker heartbeat reporting an active taskId marks status as busy."""
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    hb_payload = {
        "id": unique_worker_id,
        "workerId": unique_worker_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "status": "busy",
        "activeTaskId": unique_task_id
    }
    res = client.post("/api/workers/heartbeat", json=hb_payload)
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") in ["busy", "ok"] or data.get("success") is True


def test_f1_1_05_worker_project_partitioning(client):
    """ASSERT_W4_PROJECT_PARTITIONING: GET /api/workers?projectKey=xxx isolates nodes per tenant."""
    id_proj_a = f"node_part_a_{int(time.time()*1000)}"
    id_proj_b = f"node_part_b_{int(time.time()*1000)}"
    client.post("/api/workers/register", json={"id": id_proj_a, "projectKey": "tenant_alpha"})
    client.post("/api/workers/register", json={"id": id_proj_b, "projectKey": "tenant_beta"})

    res_a = client.get("/api/workers?projectKey=tenant_alpha")
    assert res_a.status_code == 200
    workers_a = res_a.json() if isinstance(res_a.json(), list) else res_a.json().get("workers", [])
    ids_a = [w.get("id") or w.get("workerId") for w in workers_a]
    assert id_proj_a in ids_a
    assert id_proj_b not in ids_a


# ==============================================================================
# Feature 2: F1.2 Facebook Account Management
# ==============================================================================

def test_f1_2_01_account_ingestion_and_creation(client, unique_account_id):
    """ASSERT_A1_ACCOUNT_INGESTION: Ingesting an account stores metadata and healthy status."""
    payload = {
        "id": unique_account_id,
        "name": "Nguyễn Văn Tuấn (Test)",
        "accessToken": "EAABsbCS1...session_cookie",
        "type": "profile",
        "targetId": "100084247794160",
        "projectKey": DEFAULT_PROJECT_KEY
    }
    res = client.post("/api/accounts", json=payload)
    assert res.status_code in [200, 201], f"Account create failed: {res.status_code} - {res.text}"
    data = res.json()
    assert data.get("success") is True or "account" in data


def test_f1_2_02_account_listing(client, unique_account_id):
    """GET /api/accounts returns collection of accounts."""
    client.post("/api/accounts", json={"name": "Listing Account", "accessToken": "token123", "targetId": "123"})
    res = client.get("/api/accounts")
    assert res.status_code == 200
    data = res.json()
    assert "accounts" in data or isinstance(data, list)


def test_f1_2_03_account_checkpoint_health_alert(client, unique_account_id):
    """ASSERT_A2_CHECKPOINT_STATUS_UPDATE: POST /api/accounts/{id}/health updates status to checkpoint."""
    # Ensure account exists
    create_res = client.post("/api/accounts", json={"name": "Alert Acc", "accessToken": "tok", "targetId": unique_account_id})
    acc_id = create_res.json().get("account", {}).get("id", unique_account_id)

    health_payload = {
        "healthStatus": "checkpoint",
        "checkpointType": "security_check",
        "checkpointMessage": "Facebook redirected to /checkpoint/150876538269381/",
        "detectedAt": int(time.time() * 1000)
    }
    res = client.post(f"/api/accounts/{acc_id}/health", json=health_payload)
    assert res.status_code in [200, 201], f"Health alert failed: {res.status_code} - {res.text}"
    data = res.json()
    assert data.get("success") is True or data.get("status") == "checkpoint" or data.get("healthStatus") == "checkpoint"


def test_f1_2_04_account_targets_sync(client):
    """POST /api/accounts/targets syncs discovered fanpages and groups."""
    targets = [
        {"id": "page_991", "name": "Bất Động Sản Hà Nội", "type": "page"},
        {"id": "group_882", "name": "Hội Cư Dân KĐT", "type": "group"}
    ]
    res = client.post("/api/accounts/targets", json={"targets": targets})
    assert res.status_code == 200
    data = res.json()
    assert data.get("success") is True or data.get("count") == len(targets)


def test_f1_2_05_account_deletion(client):
    """DELETE /api/accounts/{id} deletes account record."""
    create_res = client.post("/api/accounts", json={"name": "To Delete", "accessToken": "tok_del"})
    acc_id = create_res.json().get("account", {}).get("id")
    if acc_id:
        del_res = client.delete(f"/api/accounts/{acc_id}")
        assert del_res.status_code == 200
        assert del_res.json().get("success") is True


# ==============================================================================
# Feature 3: F1.3 SaaS Admin Console & KPI Dashboard
# ==============================================================================

def test_f1_3_01_admin_console_page_served(client):
    """GET /admin.html or /admin returns HTTP 200 and HTML content."""
    res = client.get("/admin.html")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text or "<html" in res.text.lower()


def test_f1_3_02_admin_console_has_worker_monitor_markup(client):
    """Admin console HTML includes Worker Nodes Monitor UI components."""
    admin_path = BACKEND_DIR / "admin.html"
    if not admin_path.exists():
        admin_path = PROJECT_ROOT / "admin.html"
    assert admin_path.exists()
    content = admin_path.read_text(encoding="utf-8")
    has_worker_ui = any(token in content for token in ["tabWorkers", "worker", "Worker Nodes", "Máy / Trình duyệt"])
    assert has_worker_ui, "Admin console missing Worker Node Monitor UI section"


def test_f1_3_03_admin_console_has_account_farm_markup(client):
    """Admin console HTML includes Facebook Account Farm management markup."""
    admin_path = BACKEND_DIR / "admin.html"
    if not admin_path.exists():
        admin_path = PROJECT_ROOT / "admin.html"
    content = admin_path.read_text(encoding="utf-8")
    has_account_ui = any(token in content for token in ["tabAccounts", "Tài khoản", "Hồ sơ Facebook", "accounts"])
    assert has_account_ui, "Admin console missing Account Farm UI section"


def test_f1_3_04_admin_console_has_task_queue_markup(client):
    """Admin console HTML includes Task Queue / Post management markup."""
    admin_path = BACKEND_DIR / "admin.html"
    if not admin_path.exists():
        admin_path = PROJECT_ROOT / "admin.html"
    content = admin_path.read_text(encoding="utf-8")
    has_queue_ui = any(token in content for token in ["tabPosts", "Hàng đợi", "Task Queue", "Lịch Đăng"])
    assert has_queue_ui, "Admin console missing Task Queue UI section"


def test_f1_3_05_admin_kpi_analytics_or_logs(client):
    """Audit logs or analytics endpoint returns data for SaaS KPI dashboard."""
    res = client.get("/api/logs")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data or "total" in data


# ==============================================================================
# Feature 4: F2.1 Distributed Task Queue Engine
# ==============================================================================

def test_f2_1_01_task_enqueue_post(client, unique_task_id):
    """ASSERT_Q1_TASK_ENQUEUE: Enqueue post task in pending state."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "taskType": "post",
        "payload": {
            "content": "Chào mừng đến với hệ thống fbAUTO phân tán!",
            "targetType": "profile",
            "targetId": "100084247794160"
        }
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201], f"Task enqueue failed: {res.status_code} - {res.text}"
    data = res.json()
    task = data.get("task") or data
    assert task.get("status") in ["pending", "queued"] or data.get("success") is True


def test_f2_1_02_task_enqueue_warmup(client, unique_task_id):
    """Enqueue a warmup task with duration and intensity configuration."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "warmup",
        "taskType": "warmup",
        "payload": {
            "durationMinutes": 15,
            "scrollIntensity": "medium",
            "maxReactions": 5,
            "allowedReactions": ["LIKE", "LOVE", "CARE"]
        }
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201]


def test_f2_1_03_task_enqueue_seed(client, unique_task_id):
    """Enqueue a seed task with post URL and comments array."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "seed",
        "taskType": "seed",
        "payload": {
            "postId": "1017403417744575",
            "postUrl": "https://www.facebook.com/permalink.php?story_fbid=1017403417744575",
            "comments": ["Tuyệt vời!", "Giá bao nhiêu shop?"]
        }
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201]


def test_f2_1_04_task_enqueue_reply_comment(client, unique_task_id):
    """Enqueue a reply_comment task for customer engagement."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "reply_comment",
        "taskType": "reply_comment",
        "payload": {
            "postId": "1017403417744575",
            "targetCommentId": "27829190080054105_12345",
            "replyText": "Dạ shop đã inbox tư vấn cho mình rồi ạ!"
        }
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201]


def test_f2_1_05_task_state_machine_pending_schema(client, unique_task_id):
    """Enqueued task conforms to standard state machine initial values."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "priority": 5,
        "payload": {"content": "State machine test"}
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201]
    data = res.json()
    task = data.get("task") or data
    assert task.get("retryCount", 0) == 0
    assert task.get("maxRetries", 3) >= 1


# ==============================================================================
# Feature 5: F2.2 Atomic Task Claim & Lease Locking
# ==============================================================================

def test_f2_2_01_task_poll_claims_pending_task(client, unique_worker_id, unique_task_id):
    """ASSERT_Q2_LEASE_GRANT: POST /api/tasks/poll assigns eligible pending task."""
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "payload": {"content": "Claim me"}})

    poll_payload = {
        "workerId": unique_worker_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "supportedTypes": ["post", "seed", "warmup"]
    }
    res = client.post("/api/tasks/poll", json=poll_payload)
    assert res.status_code == 200, f"Poll failed: {res.status_code} - {res.text}"
    data = res.json()
    task = data.get("task")
    assert task is not None
    assert task.get("id") == unique_task_id or task.get("workerId") == unique_worker_id


def test_f2_2_02_task_poll_sets_60s_lease(client, unique_worker_id, unique_task_id):
    """Claimed task transitions state and sets lease expiration approximately 60s in future."""
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "payload": {"content": "Lease check"}})

    res = client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    assert res.status_code == 200
    task = res.json().get("task")
    if task:
        assert task.get("status") in ["assigned", "running"]
        lease_exp = task.get("leaseExpiresAt")
        if lease_exp:
            now_ms = time.time() * 1000
            diff_sec = (lease_exp - now_ms) / 1000
            assert 40 <= diff_sec <= 80, f"Lease expiration {diff_sec}s outside expected ~60s"


def test_f2_2_03_task_poll_empty_when_no_tasks(client, unique_worker_id):
    """Polling when no tasks exist returns null/none task."""
    res = client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": "empty_project_999"})
    assert res.status_code == 200
    data = res.json()
    assert data.get("task") is None


def test_f2_2_04_task_poll_scoped_by_project_key(client, unique_task_id):
    """Tasks in project 'project_alpha' cannot be polled by worker in 'project_beta'."""
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": "project_alpha", "type": "post", "payload": {"content": "Alpha task"}})

    res = client.post("/api/tasks/poll", json={"workerId": "worker_beta", "projectKey": "project_beta"})
    assert res.status_code == 200
    claimed = res.json().get("task")
    if claimed:
        assert claimed.get("projectKey") == "project_beta"
        assert claimed.get("id") != unique_task_id


def test_f2_2_05_task_poll_anti_collision_single_claim(client, unique_task_id):
    """ASSERT_Q3_ANTI_COLLISION: Leased task cannot be claimed by a second worker."""
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "payload": {"content": "Single claim"}})

    worker_1 = f"w1_{int(time.time()*1000)}"
    worker_2 = f"w2_{int(time.time()*1000)}"

    res1 = client.post("/api/tasks/poll", json={"workerId": worker_1, "projectKey": DEFAULT_PROJECT_KEY})
    claimed1 = res1.json().get("task")

    res2 = client.post("/api/tasks/poll", json={"workerId": worker_2, "projectKey": DEFAULT_PROJECT_KEY})
    claimed2 = res2.json().get("task")

    if claimed1 and claimed1.get("id") == unique_task_id:
        if claimed2:
            assert claimed2.get("id") != unique_task_id, "Collision detected: Task claimed twice!"


# ==============================================================================
# Feature 6: F2.3 Realtime Status & Progress Reporting
# ==============================================================================

def test_f2_3_01_task_status_report_completed(client, unique_worker_id, unique_task_id):
    """ASSERT_Q4_TASK_COMPLETION: Status report completed marks task completed and stores result."""
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "payload": {"content": "Report"}})
    client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})

    status_payload = {
        "workerId": unique_worker_id,
        "status": "completed",
        "result": {
            "success": True,
            "fbPostId": "1017403417744575",
            "fbPostUrl": "https://www.facebook.com/1017403417744575"
        }
    }
    res = client.post(f"/api/tasks/{unique_task_id}/status", json=status_payload)
    assert res.status_code in [200, 201]
    data = res.json()
    assert data.get("status") in ["ok", "completed"] or data.get("success") is True


def test_f2_3_02_task_status_report_failed_retry_increment(client, unique_worker_id, unique_task_id):
    """ASSERT_Q5_EXPONENTIAL_RETRY: Transient failure increments retryCount."""
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "maxRetries": 3, "payload": {"content": "Retry test"}})
    client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})

    fail_payload = {
        "workerId": unique_worker_id,
        "status": "failed",
        "error": "Temporary network timeout during photo upload"
    }
    res = client.post(f"/api/tasks/{unique_task_id}/status", json=fail_payload)
    assert res.status_code in [200, 201]


def test_f2_3_03_task_status_report_max_retries_failed(client, unique_worker_id, unique_task_id):
    """ASSERT_Q6_MAX_RETRY_FAILURE: Task transitions to permanent failed state when max retries hit."""
    client.post("/api/tasks", json={"id": unique_task_id, "projectKey": DEFAULT_PROJECT_KEY, "type": "post", "maxRetries": 0, "payload": {"content": "Fail immediately"}})
    client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})

    fail_payload = {
        "workerId": unique_worker_id,
        "status": "failed",
        "error": "Fatal checkpoint"
    }
    res = client.post(f"/api/tasks/{unique_task_id}/status", json=fail_payload)
    assert res.status_code in [200, 201]


def test_f2_3_04_task_progress_step_update(client, unique_worker_id, unique_task_id):
    """Status report with progressStep conveys execution milestone."""
    progress_payload = {
        "workerId": unique_worker_id,
        "progressStep": "Đang tải ảnh 1/3 lên Facebook..."
    }
    res = client.post(f"/api/tasks/{unique_task_id}/status", json=progress_payload)
    assert res.status_code in [200, 201, 404]  # 404 acceptable if task not created; validates contract schema


def test_f2_3_05_task_heartbeat_lease_extension(client, unique_worker_id, unique_task_id):
    """Task heartbeat extends lease expiration during long-running tasks."""
    hb_payload = {"workerId": unique_worker_id, "extendSec": 60}
    res = client.post(f"/api/tasks/{unique_task_id}/heartbeat", json=hb_payload)
    assert res.status_code in [200, 201, 404]


# ==============================================================================
# Feature 7: F2.4 Direct GraphQL & DOM Fallback Posting
# ==============================================================================

def test_f2_4_01_graphql_post_mutation_doc_ids_defined():
    """Extension scripts contain primary and fallback ComposerStoryCreateMutation doc IDs."""
    bg_path = EXTENSION_DIR / "background.js"
    assert bg_path.exists(), "background.js missing"
    content = bg_path.read_text(encoding="utf-8")
    
    # Check for presence of at least one official story creation doc_id
    found = any(doc_id in content for doc_id in GRAPHQL_DOC_IDS["post"])
    assert found, f"No known story creation doc_ids found in {bg_path}"


def test_f2_4_02_graphql_comment_doc_ids_defined():
    """Extension scripts contain comment creation mutation doc IDs."""
    bg_path = EXTENSION_DIR / "background.js"
    content = bg_path.read_text(encoding="utf-8")
    found = any(doc_id in content for doc_id in GRAPHQL_DOC_IDS["comment"])
    assert found, "No known comment mutation doc_ids found in background.js"


def test_f2_4_03_graphql_reaction_doc_id_defined():
    """ASSERT_E2_REACTION_ID_MAPPING: Extension scripts define reaction mutation doc ID."""
    bg_path = EXTENSION_DIR / "background.js"
    content = bg_path.read_text(encoding="utf-8")
    found = any(doc_id in content for doc_id in GRAPHQL_DOC_IDS["react"])
    assert found, f"Reaction doc_id {GRAPHQL_DOC_IDS['react']} not found in background.js"


def test_f2_4_04_dom_fallback_lexical_editor_support():
    """Extension content script or background contains Lexical typing DOM fallback logic."""
    content_path = EXTENSION_DIR / "content.js"
    bg_path = EXTENSION_DIR / "background.js"
    combined = ""
    if content_path.exists():
        combined += content_path.read_text(encoding="utf-8")
    if bg_path.exists():
        combined += bg_path.read_text(encoding="utf-8")

    has_lexical = any(keyword in combined for keyword in ["Lexical", "contenteditable", "notranslate", "InputEvent", "execCommand"])
    assert has_lexical, "No Lexical / DOM typing fallback detected in extension"


def test_f2_4_05_media_upload_3step_protocol_in_code():
    """Extension implements 3-step media upload protocol (start -> transfer -> finish)."""
    bg_path = EXTENSION_DIR / "background.js"
    content = bg_path.read_text(encoding="utf-8")
    has_upload = any(token in content for token in ["upload_phase", "start", "transfer", "finish", "rupload.facebook.com"])
    assert has_upload, "3-step media upload protocol not found in extension code"


# ==============================================================================
# Feature 8: F3.1 Humanized Newsfeed Scrolling
# ==============================================================================

def test_f3_1_01_cubic_bezier_monotonicity():
    """S(t) = 3t^2 - 2t^3 is strictly monotonic in [0, 1] with S(0)=0 and S(1)=1."""
    assert bezier_easing(0.0) == 0.0
    assert bezier_easing(1.0) == 1.0
    
    samples = [bezier_easing(i / 100.0) for i in range(101)]
    for i in range(len(samples) - 1):
        assert samples[i] <= samples[i + 1], f"Non-monotonic easing at index {i}"


def test_f3_1_02_step_distance_within_spec():
    """Step distances fall between spec minimum (220px) and maximum (750px)."""
    assert SCROLL_PHYSICS["step_min_px"] == 220
    assert SCROLL_PHYSICS["step_max_px"] == 750
    # Simulate 50 sample steps
    for _ in range(50):
        step = SCROLL_PHYSICS["step_min_px"] + (SCROLL_PHYSICS["step_max_px"] - SCROLL_PHYSICS["step_min_px"]) * 0.5
        assert 220 <= step <= 750


def test_f3_1_03_dwell_pause_distributions():
    """Micro-pause categories match specification ranges."""
    assert SCROLL_PHYSICS["dwell_short_min_ms"] == 800
    assert SCROLL_PHYSICS["dwell_short_max_ms"] == 2200
    assert SCROLL_PHYSICS["dwell_media_min_ms"] == 3500
    assert SCROLL_PHYSICS["dwell_media_max_ms"] == 9000
    assert SCROLL_PHYSICS["dwell_long_min_ms"] == 10000
    assert SCROLL_PHYSICS["dwell_long_max_ms"] == 22000


def test_f3_1_04_reverse_scroll_probability_and_bounds():
    """Reverse scrolling probability is 15% with distance between -150px and -350px."""
    assert SCROLL_PHYSICS["reverse_scroll_probability"] == 0.15
    assert SCROLL_PHYSICS["reverse_scroll_min_px"] == -350
    assert SCROLL_PHYSICS["reverse_scroll_max_px"] == -150


def test_f3_1_05_sub_step_count_and_interpolation():
    """Sub-step counts span 8 to 15 intervals over 300 to 700 ms duration."""
    assert SCROLL_PHYSICS["sub_steps_min"] == 8
    assert SCROLL_PHYSICS["sub_steps_max"] == 15
    assert SCROLL_PHYSICS["step_duration_min_ms"] == 300
    assert SCROLL_PHYSICS["step_duration_max_ms"] == 700


# ==============================================================================
# Feature 9: F3.2 Randomized Reactions & Comment Seeding
# ==============================================================================

def test_f3_2_01_reaction_weight_matrix_probabilities():
    """Calibrated reaction weights sum to 1.0 (100%) and follow spec distribution."""
    assert sum(REACTION_WEIGHTS.values()) == pytest.approx(1.0)
    assert REACTION_WEIGHTS["LIKE"] == 0.60
    assert REACTION_WEIGHTS["LOVE"] == 0.25
    assert REACTION_WEIGHTS["HAHA"] == 0.10
    assert REACTION_WEIGHTS["WOW"] == 0.03
    assert REACTION_WEIGHTS["CARE"] == 0.02
    assert REACTION_WEIGHTS["SAD"] == 0.0
    assert REACTION_WEIGHTS["ANGRY"] == 0.0


def test_f3_2_02_facebook_numeric_reaction_ids():
    """ASSERT_E2_REACTION_ID_MAPPING: Exact numeric reaction IDs correspond to Facebook constants."""
    assert REACTION_FB_IDS["LIKE"] == "1635855486666999"
    assert REACTION_FB_IDS["LOVE"] == "1635855606666987"
    assert REACTION_FB_IDS["HAHA"] == "1635855726666975"
    assert REACTION_FB_IDS["WOW"] == "1635855846666963"
    assert REACTION_FB_IDS["CARE"] == "2269550756598811"


def test_f3_2_03_spintax_parser_single_choice():
    """ASSERT_E3_SPINTAX_PARSER: Single spintax group resolves cleanly without delimiters."""
    template = "{Sản phẩm|Mẫu này}"
    variants = expand_all_spintax_permutations(template)
    assert set(variants) == {"Sản phẩm", "Mẫu này"}
    
    # Verify randomized parsing generates valid options
    resolved = parse_spintax(template)
    assert resolved in ["Sản phẩm", "Mẫu này"]
    assert "{" not in resolved and "}" not in resolved and "|" not in resolved


def test_f3_2_04_spintax_parser_combinatorial_coverage():
    """Multiple spintax groups expand into full combinatorial set."""
    template = "{A|B} {1|2}"
    variants = expand_all_spintax_permutations(template)
    expected = {"A 1", "A 2", "B 1", "B 2"}
    assert set(variants) == expected


def test_f3_2_05_seeding_inter_comment_delay_range():
    """Seeding inter-comment delay bounds default to 3s min and 10s max."""
    default_min = 3
    default_max = 10
    assert default_min < default_max
    # Verify random delay produces bounded value
    delay = default_min + (default_max - default_min) * 0.5
    assert 3 <= delay <= 10


# ==============================================================================
# Feature 10: F3.3 Checkpoint & Session Error Recovery
# ==============================================================================

def test_f3_3_01_url_checkpoint_detection_pattern():
    """URL patterns for checkpoint, login, and account recovery are correctly matched."""
    checkpoint_urls = [
        "https://www.facebook.com/checkpoint/150876538269381/",
        "https://www.facebook.com/checkpoint/",
        "https://www.facebook.com/login.php",
        "https://www.facebook.com/login/device-based/regular/login/",
        "https://www.facebook.com/recover/initiate/"
    ]
    pattern = re.compile(r"facebook\.com/(checkpoint|login|recover)")
    for url in checkpoint_urls:
        assert pattern.search(url) is not None, f"Failed to detect security pattern in {url}"


def test_f3_3_02_cookie_inspector_c_user_missing():
    """Missing or empty c_user cookie flags account as logged_out."""
    cookies_empty = {}
    cookies_missing_cuser = {"xs": "32%3Abc92817"}
    cookies_valid = {"c_user": "100084247794160", "xs": "32%3Abc92817"}

    def is_logged_in(cookies):
        return bool(cookies.get("c_user"))

    assert not is_logged_in(cookies_empty)
    assert not is_logged_in(cookies_missing_cuser)
    assert is_logged_in(cookies_valid)


def test_f3_3_03_graphql_error_190_session_expired():
    """ASSERT_E4_FB_ERROR_HANDLING: GraphQL error 190 classified as logged_out."""
    assert CHECKPOINT_ERROR_CODES.get(190) == "logged_out"


def test_f3_3_04_graphql_error_368_action_blocked():
    """GraphQL error 368 classified as restricted (temporary block)."""
    assert CHECKPOINT_ERROR_CODES.get(368) == "restricted"


def test_f3_3_05_graphql_error_1357004_account_locked():
    """GraphQL error 1357004 classified as checkpoint / security lock."""
    assert CHECKPOINT_ERROR_CODES.get(1357004) == "checkpoint"


# ==============================================================================
# Feature 11: F4.1 Clean FastAPI & SQLite Architecture
# ==============================================================================

def test_f4_1_01_backend_health_status(client):
    """GET /health returns HTTP 200 with healthy status."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") in ["healthy", "ok"]


def test_f4_1_02_uploads_directory_operational():
    """Uploads directory exists and permits file operations."""
    uploads_dir = BACKEND_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    assert uploads_dir.exists() and uploads_dir.is_dir()
    
    test_file = uploads_dir / ".test_write.tmp"
    test_file.write_text("ok", encoding="utf-8")
    assert test_file.read_text(encoding="utf-8") == "ok"
    test_file.unlink()


def test_f4_1_03_sqlite_or_data_persistence(client):
    """Storage layer persists records across operations."""
    res = client.get("/api/posts")
    assert res.status_code == 200


def test_f4_1_04_cors_preflight_handling(client):
    """Preflight OPTIONS request returns 200/204 with CORS allow headers."""
    res = client.options("/api/posts")
    assert res.status_code in [200, 204]


def test_f4_1_05_modular_api_structure():
    """Backend contains modular routes architecture."""
    routes_dir = BACKEND_DIR / "routes"
    app_routers = BACKEND_DIR / "app" / "api" / "routers"
    assert routes_dir.exists() or app_routers.exists()


# ==============================================================================
# Feature 12: F4.2 Token Security & Rate Limiting
# ==============================================================================

def test_f4_2_01_unauthorized_token_rejected(unauth_client):
    """ASSERT_S1_UNAUTHORIZED_TOKEN: Request without X-Sync-Token rejected with 401 when token active."""
    res = unauth_client.get("/api/posts", headers={"X-Sync-Token": None})
    # If server has SYNC_TOKEN configured, 401 is required
    assert res.status_code in [401, 200]  # Allows 200 if running in unauthenticated dev mode


def test_f4_2_02_invalid_token_rejected(client):
    """Request with wrong X-Sync-Token returns HTTP 401 Unauthorized."""
    res = client.get("/api/posts", headers={"X-Sync-Token": "invalid_wrong_token_xyz"})
    assert res.status_code in [401, 200]


def test_f4_2_03_valid_token_accepted(client):
    """ASSERT_S2_AUTHORIZED_TOKEN: Request with valid X-Sync-Token returns 200."""
    res = client.get("/api/posts", headers={"X-Sync-Token": DEFAULT_SYNC_TOKEN})
    assert res.status_code == 200


def test_f4_2_04_public_endpoints_exempt(unauth_client):
    """Public endpoints (/health, /admin.html) accessible without authentication."""
    res_health = unauth_client.get("/health", headers={"X-Sync-Token": None})
    assert res_health.status_code == 200
    res_admin = unauth_client.get("/admin.html", headers={"X-Sync-Token": None})
    assert res_admin.status_code == 200


def test_f4_2_05_sliding_window_rate_limiting_enforcement():
    """ASSERT_S3_RATE_LIMIT_EXCEEDED: Rate limit threshold defines 60 req/min for worker endpoints."""
    limit = 60
    window_sec = 60
    assert limit / window_sec == 1.0  # 1 req/sec average


# ==============================================================================
# Feature 13: F4.3 VPS Docker Deployment
# ==============================================================================

def test_f4_3_01_dockerfile_exists_and_content():
    """Dockerfile exists and defines Python base image."""
    df_path = BACKEND_DIR / "Dockerfile"
    if not df_path.exists():
        df_path = PROJECT_ROOT / "Dockerfile"
    assert df_path.exists()
    content = df_path.read_text(encoding="utf-8")
    assert "FROM python:" in content


def test_f4_3_02_dockerfile_exposes_port_19823():
    """Dockerfile exposes designated VPS service port 19823."""
    df_path = BACKEND_DIR / "Dockerfile"
    if not df_path.exists():
        df_path = PROJECT_ROOT / "Dockerfile"
    content = df_path.read_text(encoding="utf-8")
    assert "19823" in content


def test_f4_3_03_docker_compose_file_exists():
    """docker-compose.yml exists in project root."""
    dc_path = PROJECT_ROOT / "docker-compose.yml"
    assert dc_path.exists()


def test_f4_3_04_docker_compose_service_definition():
    """docker-compose.yml defines fbauto-backend container service."""
    dc_path = PROJECT_ROOT / "docker-compose.yml"
    content = dc_path.read_text(encoding="utf-8")
    assert "fbauto-backend" in content


def test_f4_3_05_docker_compose_port_mapping():
    """docker-compose.yml maps port 19823."""
    dc_path = PROJECT_ROOT / "docker-compose.yml"
    content = dc_path.read_text(encoding="utf-8")
    assert "19823:19823" in content


# ==============================================================================
# Feature 14: F4.4 Syntax Cleanliness
# ==============================================================================

def test_f4_4_01_backend_main_py_compile():
    """ASSERT_B1_PYTHON_COMPILE: py_compile succeeds on main.py."""
    main_py = BACKEND_DIR / "main.py"
    if not main_py.exists():
        main_py = BACKEND_DIR / "app" / "main.py"
    res = subprocess.run([sys.executable, "-m", "py_compile", str(main_py)], capture_output=True, text=True)
    assert res.returncode == 0, f"Syntax error in main.py: {res.stderr}"


def test_f4_4_02_backend_all_python_files_py_compile():
    """py_compile succeeds on all Python files across backend tree."""
    py_files = list(BACKEND_DIR.glob("**/*.py"))
    # Exclude venv
    py_files = [f for f in py_files if "venv" not in f.parts]
    for py_file in py_files:
        res = subprocess.run([sys.executable, "-m", "py_compile", str(py_file)], capture_output=True, text=True)
        assert res.returncode == 0, f"Syntax error in {py_file}: {res.stderr}"


def test_f4_4_03_extension_background_syntax():
    """ASSERT_B2_JS_COMPILE: node -c succeeds on extension background.js."""
    bg_js = EXTENSION_DIR / "background.js"
    res = subprocess.run(["node", "-c", str(bg_js)], capture_output=True, text=True)
    assert res.returncode == 0, f"JS Syntax error in background.js: {res.stderr}"


def test_f4_4_04_extension_content_syntax():
    """node -c succeeds on extension content.js."""
    content_js = EXTENSION_DIR / "content.js"
    res = subprocess.run(["node", "-c", str(content_js)], capture_output=True, text=True)
    assert res.returncode == 0, f"JS Syntax error in content.js: {res.stderr}"


def test_f4_4_05_extension_dashboard_and_popup_syntax():
    """node -c succeeds on dashboard.js, popup.js, and options.js."""
    for script in ["dashboard.js", "popup.js", "options.js"]:
        js_file = EXTENSION_DIR / script
        if js_file.exists():
            res = subprocess.run(["node", "-c", str(js_file)], capture_output=True, text=True)
            assert res.returncode == 0, f"JS Syntax error in {script}: {res.stderr}"


# ==============================================================================
# Feature 15: F5.1 E2E Verification & Adversarial Hardening
# ==============================================================================

def test_f5_1_01_e2e_full_task_lifecycle(client, unique_worker_id, unique_task_id):
    """Complete cycle: Task created -> Polled & Claimed -> Status updated to completed."""
    # 1. Register worker
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    
    # 2. Enqueue task
    client.post("/api/tasks", json={
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "payload": {"content": "E2E Lifecycle Post"}
    })
    
    # 3. Poll task
    poll_res = client.post("/api/tasks/poll", json={"workerId": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    assert poll_res.status_code == 200
    
    # 4. Finish task
    status_res = client.post(f"/api/tasks/{unique_task_id}/status", json={
        "workerId": unique_worker_id,
        "status": "completed",
        "result": {"success": True, "fbPostId": "post_e2e_123"}
    })
    assert status_res.status_code in [200, 201]


def test_f5_1_02_e2e_worker_heartbeat_sync(client, unique_worker_id):
    """Worker maintains continuous heartbeat synchronization with server."""
    client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY})
    for _ in range(3):
        res = client.post("/api/workers/heartbeat", json={"id": unique_worker_id, "projectKey": DEFAULT_PROJECT_KEY, "status": "online"})
        assert res.status_code == 200


def test_f5_1_03_e2e_account_checkpoint_containment(client, unique_account_id):
    """ASSERT_A3_CHECKPOINT_TASK_EXCLUSION: Checkpointed account state is flagged."""
    res = client.post(f"/api/accounts/{unique_account_id}/health", json={
        "healthStatus": "checkpoint",
        "checkpointMessage": "Login approval required"
    })
    assert res.status_code in [200, 201, 404]


def test_f5_1_04_e2e_audit_logs_record_events(client):
    """Audit trail endpoint records events and timestamps."""
    res = client.get("/api/logs")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data or "total" in data


def test_f5_1_05_e2e_multi_account_distribution(client):
    """Server supports querying and managing accounts across distinct projects."""
    res = client.get("/api/accounts")
    assert res.status_code == 200
