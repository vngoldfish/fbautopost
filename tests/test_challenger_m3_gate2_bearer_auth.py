"""
tests/test_challenger_m3_gate2_bearer_auth.py
Adversarial Empirical Stress Tests for Bearer Token Authentication (Milestone 3 Gate 2)
Author: challenger_m3_gate2_1

Covers:
1. Valid RFC 6750 Bearer tokens across all backend endpoints
2. Case-insensitivity (Bearer, bearer, BEARER, bEaReR)
3. Whitespace tolerance (leading/trailing whitespace around token)
4. Invalid Bearer tokens (expect 401 Unauthorized)
5. Malformed Authorization headers (missing prefix, empty, bad schemes, missing space)
6. Mixed headers: X-Sync-Token vs Authorization precedence & interaction
7. Query parameter fallback vs Authorization
8. WWW-Authenticate response header validation
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend path is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.core.config import settings
from app.core.security import verify_sync_token, extract_sync_token, require_sync_token

TEST_TOKEN = "challenger_secret_token_gate2_2026"
TEST_PROJECT = "taikhoan_challenger"
TEST_WORKER = "challenger_worker_node_1"

@pytest.fixture(autouse=True)
def configure_test_token(monkeypatch):
    """Enforce non-empty SYNC_TOKEN in settings for rigorous auth testing."""
    monkeypatch.setattr(settings, "SYNC_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

@pytest.fixture
def client():
    """Create FastAPI TestClient."""
    return TestClient(app)


# ==============================================================================
# 1. VALID RFC 6750 BEARER TOKENS ACROSS ALL ENDPOINTS
# ==============================================================================

@pytest.mark.parametrize("endpoint,method", [
    ("/api/posts", "GET"),
    ("/api/workers", "GET"),
    ("/api/accounts", "GET"),
    ("/api/tasks", "GET"),
    ("/api/projects", "GET"),
    ("/api/settings", "GET"),
    ("/api/logs", "GET"),
    ("/sync/status", "GET"),
    ("/sync/config", "GET"),
    ("/sync/theme", "GET"),
])
def test_valid_bearer_token_across_endpoints(client, endpoint, method):
    """Standard Bearer header grants 200 OK across read/list endpoints."""
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}"
    }
    res = client.request(method, endpoint, headers=headers)
    assert res.status_code == 200, f"Expected 200 for {endpoint}, got {res.status_code}: {res.text}"


def test_valid_bearer_on_worker_poll_endpoint(client):
    """Bearer auth succeeds on /api/tasks/poll when tenant headers are present."""
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "X-Project-Key": TEST_PROJECT,
        "X-Worker-Id": TEST_WORKER
    }
    payload = {
        "workerId": TEST_WORKER,
        "supportedTypes": ["post", "seed", "warmup"]
    }
    res = client.post("/api/tasks/poll", json=payload, headers=headers)
    assert res.status_code == 200, f"Poll failed: {res.status_code} {res.text}"
    assert "task" in res.json()


def test_valid_bearer_on_worker_heartbeat_endpoint(client):
    """Bearer auth succeeds on /api/workers/heartbeat when tenant headers are present."""
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "X-Project-Key": TEST_PROJECT,
        "X-Worker-Id": TEST_WORKER
    }
    payload = {
        "workerId": TEST_WORKER,
        "status": "idle"
    }
    res = client.post("/api/workers/heartbeat", json=payload, headers=headers)
    assert res.status_code == 200, f"Heartbeat failed: {res.status_code} {res.text}"


# ==============================================================================
# 2. CASE-INSENSITIVITY & SCHEME TOLERANCE
# ==============================================================================

@pytest.mark.parametrize("scheme_prefix", [
    "Bearer",
    "bearer",
    "BEARER",
    "BeArEr",
    "bEaReR",
])
def test_bearer_case_insensitivity(client, scheme_prefix):
    """RFC 6750 scheme prefix 'Bearer' is case-insensitive."""
    headers = {
        "Authorization": f"{scheme_prefix} {TEST_TOKEN}"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200, f"Failed for scheme '{scheme_prefix}': {res.status_code}"


@pytest.mark.parametrize("header_value", [
    f"Bearer   {TEST_TOKEN}",           # Multiple spaces after scheme
    f"Bearer        {TEST_TOKEN}   ",     # Leading and trailing spaces
    f"Bearer \t {TEST_TOKEN} \t",         # Tab whitespace
])
def test_bearer_whitespace_tolerance(client, header_value):
    """Whitespace around token is stripped cleanly per RFC 6750."""
    headers = {
        "Authorization": header_value
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200, f"Failed for header '{header_value}': {res.status_code}"


# ==============================================================================
# 3. INVALID BEARER TOKENS (EXPECT 401 UNAUTHORIZED)
# ==============================================================================

@pytest.mark.parametrize("invalid_token", [
    "completely_wrong_secret",
    f"{TEST_TOKEN}_suffix",
    f"prefix_{TEST_TOKEN}",
    TEST_TOKEN[:-1],                       # Truncated token
    TEST_TOKEN.upper() if TEST_TOKEN != TEST_TOKEN.upper() else "WRONG_TOKEN",
    "Bearer",                              # Token equals the word Bearer
    "null",
    "undefined",
])
def test_invalid_bearer_token_rejected(client, invalid_token):
    """Incorrect Bearer token is strictly rejected with 401."""
    headers = {
        "Authorization": f"Bearer {invalid_token}"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 401, f"Expected 401 for token '{invalid_token}', got {res.status_code}"
    body = res.json()
    assert "error" in body or "detail" in body


# ==============================================================================
# 4. MALFORMED AUTHORIZATION HEADERS (EXPECT 401 UNAUTHORIZED)
# ==============================================================================

@pytest.mark.parametrize("malformed_auth,desc", [
    ("Bearer", "Bare scheme without space or token"),
    ("bearer", "Bare scheme lowercase"),
    ("BEARER", "Bare scheme uppercase"),
    ("Bearer ", "Scheme with single trailing space, empty token"),
    ("Bearer    ", "Scheme with whitespace-only token"),
    (f"Bearer{TEST_TOKEN}", "Missing space between scheme and token"),
    (TEST_TOKEN, "Missing scheme entirely (bare token)"),
    (f"Basic {TEST_TOKEN}", "Unsupported Basic auth scheme"),
    (f"Token {TEST_TOKEN}", "Unsupported Token auth scheme"),
    (f"Digest {TEST_TOKEN}", "Unsupported Digest auth scheme"),
    (f"BearerBearer {TEST_TOKEN}", "Double scheme prefix"),
    (f"Bearer: {TEST_TOKEN}", "Colon delimiter instead of space"),
    ("", "Empty Authorization header value"),
    ("   ", "Whitespace-only Authorization header value"),
    (f"Bearer {TEST_TOKEN} extra_garbage", "Token followed by extraneous data"),
])
def test_malformed_authorization_headers(client, malformed_auth, desc):
    """Malformed Authorization headers fail safely with 401 Unauthorized."""
    headers = {
        "Authorization": malformed_auth
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 401, f"Expected 401 for '{desc}' (got {res.status_code})"


# ==============================================================================
# 5. MIXED HEADERS: X-Sync-Token vs Authorization INTERACTION & PRECEDENCE
# ==============================================================================

def test_mixed_headers_both_valid(client):
    """When both X-Sync-Token and Authorization: Bearer are valid, request succeeds."""
    headers = {
        "X-Sync-Token": TEST_TOKEN,
        "Authorization": f"Bearer {TEST_TOKEN}"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200


def test_mixed_headers_valid_sync_token_with_invalid_bearer(client):
    """X-Sync-Token takes precedence: valid X-Sync-Token succeeds even if Bearer is invalid."""
    headers = {
        "X-Sync-Token": TEST_TOKEN,
        "Authorization": "Bearer invalid_bearer_token"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200


def test_mixed_headers_valid_sync_token_with_malformed_bearer(client):
    """X-Sync-Token takes precedence: valid X-Sync-Token succeeds even if Bearer is malformed."""
    headers = {
        "X-Sync-Token": TEST_TOKEN,
        "Authorization": "Bearer"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200


def test_mixed_headers_invalid_sync_token_with_valid_bearer(client):
    """
    Adversarial test: An explicitly invalid X-Sync-Token is rejected with 401,
    preventing header confusion/shadowing attacks.
    """
    headers = {
        "X-Sync-Token": "invalid_sync_token_attack",
        "Authorization": f"Bearer {TEST_TOKEN}"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 401, f"Expected 401 when X-Sync-Token is invalid, got {res.status_code}"


def test_mixed_headers_empty_sync_token_falls_through_to_bearer(client):
    """Empty string X-Sync-Token falls through to valid Authorization: Bearer."""
    headers = {
        "X-Sync-Token": "",
        "Authorization": f"Bearer {TEST_TOKEN}"
    }
    res = client.get("/api/posts", headers=headers)
    assert res.status_code == 200


# ==============================================================================
# 6. QUERY PARAMETER FALLBACK VS BEARER HEADER
# ==============================================================================

def test_query_param_fallback_when_no_headers(client):
    """Query parameter fallback works when no auth headers are provided."""
    res = client.get(f"/api/posts?token={TEST_TOKEN}")
    assert res.status_code == 200


def test_invalid_bearer_does_not_mask_with_query_param(client):
    """
    Security check: An invalid Bearer token is NOT bypassed by providing
    a valid query parameter.
    """
    headers = {
        "Authorization": "Bearer bad_token"
    }
    res = client.get(f"/api/posts?token={TEST_TOKEN}", headers=headers)
    assert res.status_code == 401


# ==============================================================================
# 7. WWW-AUTHENTICATE RESPONSE HEADER & SECURITY CONTRACT
# ==============================================================================

def test_www_authenticate_header_on_dependency_rejection():
    """Verify require_sync_token dependency sets WWW-Authenticate header on 401."""
    from fastapi import Request
    from starlette.datastructures import Headers

    # Mock unauthenticated request
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/posts",
        "headers": [(b"host", b"testserver")],
        "query_string": b"",
    }
    req = Request(scope)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        import asyncio
        asyncio.run(require_sync_token(req))

    assert exc_info.value.status_code == 401
    auth_header = exc_info.value.headers.get("WWW-Authenticate", "")
    assert "Bearer" in auth_header
    assert "X-Sync-Token" in auth_header
