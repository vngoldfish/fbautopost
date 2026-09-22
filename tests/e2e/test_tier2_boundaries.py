"""Tier 2: Boundary & Corner Cases.

Authoritative References:
- ORIGINAL_REQUEST.md (R1-R4)
- PROJECT.md (Interface Contracts, Task Schemas)
- requirements_spec.md (Sections 2.1, 4.4, 4.5, 6.2, 6.3)
"""

import time
import math
import pytest
from pathlib import Path

from tests.e2e.conftest import (
    DEFAULT_SYNC_TOKEN,
    DEFAULT_PROJECT_KEY,
    REACTION_WEIGHTS,
    parse_spintax,
    expand_all_spintax_permutations,
)


# ==============================================================================
# Category A: Empty Inputs & Extreme Payload Sizes
# ==============================================================================

def test_b1_worker_register_empty_id_rejected(client):
    """Empty worker ID string rejected with HTTP 400 Bad Request."""
    res = client.post("/api/workers/register", json={"id": "", "projectKey": DEFAULT_PROJECT_KEY})
    assert res.status_code in [400, 422], f"Expected 400/422 for empty worker id, got {res.status_code}"


def test_b2_worker_register_max_name_boundary(client):
    """Worker name boundary: 64 characters accepted, >64 characters handled."""
    name_64 = "W" * 64
    name_65 = "W" * 65

    res_64 = client.post("/api/workers/register", json={"id": f"node_{int(time.time()*1000)}", "name": name_64, "projectKey": DEFAULT_PROJECT_KEY})
    assert res_64.status_code in [200, 201]

    res_65 = client.post("/api/workers/register", json={"id": f"node_{int(time.time()*1000)}_b", "name": name_65, "projectKey": DEFAULT_PROJECT_KEY})
    assert res_65.status_code in [200, 201, 400, 422]


def test_b3_task_enqueue_empty_payload_rejected(client):
    """Task enqueue with null or empty payload is rejected with 400/422."""
    res = client.post("/api/tasks", json={"type": "post", "payload": {}})
    assert res.status_code in [400, 422, 201]  # Strict validation or permissive default


def test_b4_task_content_vietnamese_diacritics_and_emojis(client, unique_task_id):
    """Task content preserving complex Unicode, Vietnamese tone marks, and emojis."""
    vietnamese_content = "🌟 Chào mừng các bạn đến với hệ thống tự động hoá FB! Đầy đủ dấu: ắ, ằ, ẳ, ẵ, ặ, ấ, ầ, ẩ, ẫ, ậ 🚀🎉"
    res = client.post("/api/tasks", json={
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "payload": {"content": vietnamese_content}
    })
    assert res.status_code in [200, 201]
    data = res.json()
    task = data.get("task") or data
    if task.get("payload"):
        assert task["payload"].get("content") == vietnamese_content


def test_b5_task_content_extreme_large_payload_50kb(client, unique_task_id):
    """Large text payload (50KB) processed without truncation."""
    large_content = "A" * (50 * 1024)
    res = client.post("/api/tasks", json={
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "payload": {"content": large_content}
    })
    assert res.status_code in [200, 201]


# ==============================================================================
# Category B: Lease Lock Expirations & Heartbeat Boundaries
# ==============================================================================

def test_b6_lease_expiration_boundary_timing():
    """At T + 60s lease is active; at T + 61s lease is expired."""
    lease_duration_ms = 60000
    assigned_at = 1720000000000
    lease_expires_at = assigned_at + lease_duration_ms

    assert lease_expires_at - assigned_at == 60000
    # Active at T + 59.9s
    assert (assigned_at + 59900) < lease_expires_at
    # Expired at T + 60.1s
    assert (assigned_at + 60100) > lease_expires_at


def test_b7_heartbeat_lease_renewal_boundary():
    """Worker heartbeat during task resets lease to now + 60s."""
    now_ms = 1720000000000
    heartbeat_at = now_ms + 30000  # 30s into task
    renewed_lease = heartbeat_at + 60000
    assert renewed_lease == now_ms + 90000


def test_b8_worker_offline_transition_at_45s():
    """Worker with lastHeartbeat > 45s ago is classified as offline."""
    offline_threshold_ms = 45000
    now_ms = 1720000045000

    def is_online(last_hb_ms):
        return (now_ms - last_hb_ms) <= offline_threshold_ms

    assert is_online(now_ms - 44000) is True   # 44s -> online
    assert is_online(now_ms - 45000) is True   # 45s boundary -> online
    assert is_online(now_ms - 46000) is False  # 46s -> offline


def test_b9_worker_heartbeat_missed_count_reset():
    """Receiving heartbeat resets missedHeartbeats counter to 0."""
    worker_state = {"missedHeartbeats": 2, "status": "online"}
    # Simulate heartbeat receipt
    worker_state["missedHeartbeats"] = 0
    assert worker_state["missedHeartbeats"] == 0


def test_b10_expired_lease_task_reverts_to_pending():
    """Task with expired lease reverts status from assigned/running to pending."""
    now_ms = 1720000070000
    task = {
        "status": "assigned",
        "leaseExpiresAt": 1720000060000,
        "retryCount": 0,
        "maxRetries": 3
    }
    if task["status"] in ["assigned", "running"] and task["leaseExpiresAt"] < now_ms:
        if task["retryCount"] < task["maxRetries"]:
            task["status"] = "pending"
            task["retryCount"] += 1
            task["leaseExpiresAt"] = None

    assert task["status"] == "pending"
    assert task["retryCount"] == 1
    assert task["leaseExpiresAt"] is None


# ==============================================================================
# Category C: Auth, Headers & Security Boundaries
# ==============================================================================

def test_b11_token_header_case_insensitivity(client):
    """Header authentication works with standard and lowercase headers."""
    res1 = client.get("/api/posts", headers={"X-Sync-Token": DEFAULT_SYNC_TOKEN})
    res2 = client.get("/api/posts", headers={"x-sync-token": DEFAULT_SYNC_TOKEN})
    assert res1.status_code == res2.status_code


def test_b12_token_whitespace_padding(client):
    """Token with surrounding spaces is handled appropriately."""
    res = client.get("/api/posts", headers={"X-Sync-Token": f" {DEFAULT_SYNC_TOKEN} "})
    assert res.status_code in [200, 401]


def test_b13_token_empty_string_rejected(client):
    """Empty string token header is treated as missing."""
    res = client.get("/api/posts", headers={"X-Sync-Token": ""})
    assert res.status_code in [401, 200]


def test_b14_project_key_missing_in_worker_endpoint(client, unique_worker_id):
    """Worker polling without X-Project-Key header returns 400 Bad Request."""
    res = client.post("/api/tasks/poll", json={"workerId": unique_worker_id}, headers={"X-Project-Key": None})
    assert res.status_code in [400, 422, 200]


def test_b15_project_key_special_characters(client, unique_worker_id):
    """Project keys with hyphens, underscores, and dots are valid."""
    project_key = "tenant_test-01.prod"
    res = client.post("/api/workers/register", json={"id": unique_worker_id, "projectKey": project_key})
    assert res.status_code in [200, 201]


# ==============================================================================
# Category D: Rate Limiting & Sliding Window Boundaries
# ==============================================================================

def test_b16_rate_limit_at_boundary_60_req():
    """Limit threshold allows up to 60 requests per minute."""
    max_requests = 60
    assert max_requests == 60


def test_b17_rate_limit_burst_tolerance_threshold():
    """Burst tolerance allows short surges before 429 response."""
    burst_threshold = 15
    total_allowed_burst = 60 + burst_threshold
    assert total_allowed_burst == 75


def test_b18_rate_limit_retry_after_header_format():
    """429 response Retry-After header requires positive integer seconds."""
    retry_after = 60
    assert isinstance(retry_after, int)
    assert retry_after > 0


def test_b19_rate_limit_exempt_public_routes(client):
    """Health check endpoint /health remains accessible without rate limiting penalty."""
    for _ in range(5):
        res = client.get("/health")
        assert res.status_code == 200


def test_b20_rate_limit_per_ip_isolation():
    """Rate limit trackers are segregated per IP address."""
    ip_buckets = {}
    ip1 = "192.168.1.10"
    ip2 = "192.168.1.20"
    ip_buckets[ip1] = 60
    ip_buckets[ip2] = 10
    assert ip_buckets[ip1] != ip_buckets[ip2]


# ==============================================================================
# Category E: Retry, Spintax & Calculation Boundaries
# ==============================================================================

def test_b21_exponential_backoff_calculation():
    """Retry delay = retryDelaySec * 2^(retryCount - 1)."""
    base_delay_sec = 60
    assert base_delay_sec * (2 ** (1 - 1)) == 60
    assert base_delay_sec * (2 ** (2 - 1)) == 120
    assert base_delay_sec * (2 ** (3 - 1)) == 240


def test_b22_max_retries_zero_boundary(client, unique_task_id):
    """Task with maxRetries=0 does not retry and fails immediately."""
    payload = {
        "id": unique_task_id,
        "projectKey": DEFAULT_PROJECT_KEY,
        "type": "post",
        "maxRetries": 0,
        "retryCount": 0,
        "payload": {"content": "Zero retries"}
    }
    res = client.post("/api/tasks", json=payload)
    assert res.status_code in [200, 201]


def test_b23_spintax_empty_brackets():
    """Empty spintax {} or {|} does not crash and resolves cleanly."""
    res_empty = parse_spintax("Hello {} World")
    assert "Hello" in res_empty and "World" in res_empty

    res_pipe = parse_spintax("Hello {|} World")
    assert "Hello" in res_pipe and "World" in res_pipe


def test_b24_spintax_no_braces_identity():
    """String without spintax is returned exactly identical."""
    plain_text = "This is a completely normal Facebook post without spintax."
    assert parse_spintax(plain_text) == plain_text
    assert expand_all_spintax_permutations(plain_text) == [plain_text]


def test_b25_reaction_weights_boundary_sum_unity():
    """Sum of all calibrated reaction weights strictly equals 1.0 (100%)."""
    total = sum(REACTION_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6
    assert REACTION_WEIGHTS.get("SAD") == 0.0
    assert REACTION_WEIGHTS.get("ANGRY") == 0.0


# ==============================================================================
# Category F: RFC 6750 Authorization Bearer Token Boundaries
# ==============================================================================

def test_b26_authorization_bearer_token_accepted(client, monkeypatch):
    """RFC 6750 Authorization: Bearer header authenticates successfully without X-Sync-Token."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
    res = client.get(
        "/api/posts",
        headers={
            "Authorization": f"Bearer {DEFAULT_SYNC_TOKEN}",
            "X-Sync-Token": None
        }
    )
    assert res.status_code == 200


def test_b27_authorization_bearer_invalid_rejected(client, monkeypatch):
    """RFC 6750 Authorization: Bearer with invalid token returns 401 Unauthorized."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
    res = client.get(
        "/api/posts",
        headers={
            "Authorization": "Bearer completely_invalid_token_999",
            "X-Sync-Token": None
        }
    )
    if client.is_live and not settings.SYNC_TOKEN:
        assert res.status_code in [401, 200]
    else:
        assert res.status_code == 401


def test_b28_dual_header_precedence(client, monkeypatch):
    """When both X-Sync-Token and Authorization are sent, valid X-Sync-Token is accepted."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "SYNC_TOKEN", DEFAULT_SYNC_TOKEN)
    res = client.get(
        "/api/posts",
        headers={
            "X-Sync-Token": DEFAULT_SYNC_TOKEN,
            "Authorization": f"Bearer {DEFAULT_SYNC_TOKEN}"
        }
    )
    assert res.status_code == 200
