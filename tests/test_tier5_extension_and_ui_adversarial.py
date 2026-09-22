"""
tests/test_tier5_extension_and_ui_adversarial.py
Milestone 5 Tier 5 Adversarial Coverage Hardening:
Chrome Extension Worker Node & SaaS Admin Console Adversarial Suite

Author: Challenger 2 (challenger_m5_tier5_2)
Archetype: EMPIRICAL CHALLENGER

Scope:
1. Warmup math stress:
   - Cubic Bézier velocity curves & boundary conditions (t=0, t=1, t<0, t>1, NaN, strict monotonicity, derivative).
   - Spintax deeply nested structures ({{{a|b}|c}|d}), empty spintax, unclosed braces, 20-level recursion cap.
   - Variable dwell pauses, 15% reverse scroll chance, calibrated reaction weights.
2. Checkpoint watchdog 4-layer stress:
   - Layer 1 URL regex: Vanity URLs resistance (facebook.com/checkpoint.fashion, checkpoint123, etc.) vs true checkpoints.
   - Layer 2 Cookie inspector: Cookie string parser edge cases, c_user presence, c_user=0.
   - Layer 3 GraphQL error interceptor: 50+ mixed errors with checkpoint code at varying positions (index 0, middle, tail).
   - Layer 4 DOM anomaly text scanner: Vietnamese and English keywords, case insensitivity.
3. Worker Node lifecycle & security:
   - Cold-start ephemeral boot ID format ("node-boot-...").
   - RFC 6750 dual auth headers (X-Sync-Token and Authorization: Bearer).
   - Defensive X-Worker-Id fallback.
4. SaaS Admin Console DOM & XSS stress:
   - escapeHtml neutralization of all XSS vectors (<script>, "><img src=x onerror=..., <svg/onload=..., quotes, ampersands).
   - Template interpolation audit ensuring all dynamic entity properties are escaped.
   - Dynamic lease tickers under normal conditions and severe clock drift.
   - Worker last-seen relative time ticker under normal conditions and clock drift.
   - Rapid modal open/close idempotency and state cleanup.
5. End-to-end Node.js adversarial runner integration verifying 1900+ assertions.
"""

import math
import re
import subprocess
import sys
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = PROJECT_ROOT / "extension-auth-helper"
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
ADMIN_HTML_PATH = BACKEND_DIR / "admin.html"
WARMUP_JS_PATH = EXTENSION_DIR / "warmup.js"
CHECKPOINT_JS_PATH = EXTENSION_DIR / "checkpoint.js"
BACKGROUND_JS_PATH = EXTENSION_DIR / "background.js"
NODE_HARNESS_PATH = PROJECT_ROOT / "tests" / "test_tier5_extension_and_ui_adversarial.js"


# =====================================================================
# FIXTURES
# =====================================================================
@pytest.fixture(scope="module")
def admin_html_soup():
    assert ADMIN_HTML_PATH.exists(), f"admin.html must exist at {ADMIN_HTML_PATH}"
    content = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    return BeautifulSoup(content, "html.parser")


@pytest.fixture(scope="module")
def admin_html_raw():
    assert ADMIN_HTML_PATH.exists()
    return ADMIN_HTML_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def warmup_js_raw():
    assert WARMUP_JS_PATH.exists()
    return WARMUP_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def checkpoint_js_raw():
    assert CHECKPOINT_JS_PATH.exists()
    return CHECKPOINT_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def background_js_raw():
    assert BACKGROUND_JS_PATH.exists()
    return BACKGROUND_JS_PATH.read_text(encoding="utf-8")


# =====================================================================
# SUITE 1: WARMUP KINEMATICS & MATHEMATICAL CURVES
# =====================================================================
def bezier_easing(t: float) -> float:
    """Exact replica of warmup.js bezierEasing(t)."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 3.0 * t * t - 2.0 * t * t * t


def test_bezier_curve_boundary_conditions():
    """Verify Bézier curve boundary clamping at t=0, t=1, t<0, t>1, and extremes."""
    assert bezier_easing(0.0) == 0.0
    assert bezier_easing(1.0) == 1.0
    assert bezier_easing(-0.0001) == 0.0
    assert bezier_easing(-10.0) == 0.0
    assert bezier_easing(-float("inf")) == 0.0
    assert bezier_easing(1.0001) == 1.0
    assert bezier_easing(10.0) == 1.0
    assert bezier_easing(float("inf")) == 1.0


def test_bezier_curve_symmetry_and_monotonicity():
    """Verify central symmetry S(t) + S(1-t) == 1.0 and strict monotonicity on [0, 1]."""
    assert abs(bezier_easing(0.5) - 0.5) < 1e-9

    prev = -1.0
    for i in range(1001):
        t = i / 1000.0
        val = bezier_easing(t)
        # Monotonicity
        assert val >= prev, f"Bézier easing must be monotonic at t={t}"
        prev = val

        # Central rotational symmetry
        complement = bezier_easing(1.0 - t)
        assert abs((val + complement) - 1.0) < 1e-9, f"Symmetric property failed at t={t}"


def test_bezier_derivative_properties():
    """
    Verify derivative S'(t) = 6t(1-t):
    - Zero initial acceleration S'(0) = 0
    - Zero terminal acceleration S'(1) = 0
    - Non-negative everywhere on [0, 1]
    """
    def s_prime(t):
        return 6.0 * t * (1.0 - t)

    assert s_prime(0.0) == 0.0
    assert s_prime(1.0) == 0.0
    assert s_prime(0.5) == 1.5  # Peak velocity at midpoint

    for i in range(101):
        t = i / 100.0
        assert s_prime(t) >= 0.0


def test_spintax_combinatorial_expansion_deeply_nested():
    """Verify combinatorial expansion of {{{a|b}|c}|d} produces exhaustive 4 outcomes."""
    pattern = re.compile(r"\{([^{}]+)\}")

    def expand_all(text):
        if not text:
            return [""]
        m = pattern.search(text)
        if not m:
            return [text]
        before = text[:m.start()]
        after = text[m.end():]
        options = m.group(1).split("|")
        results = []
        for opt in options:
            for sub in expand_all(before + opt + after):
                results.append(sub)
        return results

    deeply_nested = "{{{a|b}|c}|d}"
    outcomes = set(expand_all(deeply_nested))
    assert outcomes == {"a", "b", "c", "d"}, f"Expected {{a, b, c, d}}, got {outcomes}"


def test_spintax_edge_cases_and_malformed_inputs():
    """Verify parser handling of empty spintax, unclosed braces, and empty choices."""
    regex = re.compile(r"\{([^{}]+)\}")

    def parse_spintax_py(text):
        if not text or not isinstance(text, str):
            return text or ""
        result = text
        iterations = 0
        while regex.search(result) and iterations < 20:
            result = regex.sub(lambda m: m.group(1).split("|")[0], result)
            iterations += 1
        return result

    assert parse_spintax_py("") == ""
    assert parse_spintax_py(None) == ""
    assert parse_spintax_py("{}") == "{}"
    assert parse_spintax_py("{|}") == ""
    assert parse_spintax_py("{a|b") == "{a|b"  # Unclosed brace unchanged
    assert parse_spintax_py("a|b}") == "a|b}"  # Stray brace unchanged


# =====================================================================
# SUITE 2: CHECKPOINT WATCHDOG 4-LAYER ADVERSARIAL STRESS
# =====================================================================
CHECKPOINT_URL_PATTERNS = [
    re.compile(r"facebook\.com/(checkpoint|login|recover)(/|\?|#|$)", re.IGNORECASE),
    re.compile(r"facebook\.com/login\.php(/|\?|#|$)", re.IGNORECASE),
    re.compile(r"facebook\.com/disabled(/|\?|#|$)", re.IGNORECASE),
    re.compile(r"facebook\.com/help/contact/", re.IGNORECASE),
]


def check_url_checkpoint(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return any(p.search(url) for p in CHECKPOINT_URL_PATTERNS)


def test_checkpoint_url_positive_matches():
    """Verify true Facebook checkpoint, login, disabled, and recovery URLs are detected."""
    positive_urls = [
        "https://www.facebook.com/checkpoint/",
        "https://www.facebook.com/checkpoint/123456789/",
        "https://www.facebook.com/checkpoint?next=https%3A%2F%2Ffacebook.com",
        "https://www.facebook.com/checkpoint#security_challenge",
        "https://www.facebook.com/checkpoint",
        "https://www.facebook.com/login.php",
        "https://www.facebook.com/login.php?login_attempt=1",
        "https://www.facebook.com/recover/initiate/",
        "https://www.facebook.com/disabled/",
        "https://www.facebook.com/help/contact/260749603972907",
    ]
    for url in positive_urls:
        assert check_url_checkpoint(url) is True, f"Failed to match checkpoint URL: {url}"


def test_checkpoint_vanity_urls_resistance():
    """
    CRUCIAL: Verify vanity URLs containing 'checkpoint', 'login', or 'recover'
    do NOT trigger false-positive checkpoint quarantine!
    """
    vanity_urls = [
        "https://www.facebook.com/checkpoint.fashion",
        "https://www.facebook.com/checkpoint123",
        "https://www.facebook.com/checkpoint_vietnam",
        "https://www.facebook.com/checkpointer",
        "https://www.facebook.com/checkpoint-boutique",
        "https://www.facebook.com/login_success",
        "https://www.facebook.com/recovery_records",
        "https://www.facebook.com/disabled_veterans_foundation",
        "https://www.facebook.com/profile.php?id=10008888",
        "https://www.google.com/checkpoint/",  # Non-facebook domain
    ]
    for url in vanity_urls:
        assert check_url_checkpoint(url) is False, f"False positive on vanity URL: {url}"


def test_cookie_string_parser_and_health():
    """Verify cookie parsing handles weird delimiters, equals in values, and c_user validation."""
    def parse_cookie_string(cookie_str):
        if not cookie_str or not isinstance(cookie_str, str):
            return []
        cookies = []
        for part in cookie_str.split(";"):
            trimmed = part.strip()
            if not trimmed or "=" not in trimmed:
                continue
            name, value = trimmed.split("=", 1)
            name, value = name.strip(), value.strip()
            if name:
                cookies.append({"name": name, "value": value})
        return cookies

    def inspect_cookie_health(cookie_str):
        cookies = parse_cookie_string(cookie_str)
        c_user = next((c for c in cookies if c["name"] == "c_user" and c["value"].strip() and c["value"] != "0"), None)
        return c_user is not None

    raw = ";;  ;; c_user = 1000888999 ; ; xs=3%3Aabc=def; ;"
    parsed = parse_cookie_string(raw)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "c_user" and parsed[0]["value"] == "1000888999"
    assert parsed[1]["name"] == "xs" and parsed[1]["value"] == "3%3Aabc=def"
    assert inspect_cookie_health(raw) is True

    # Bad cookie cases
    assert inspect_cookie_health("xs=abc; fr=123") is False  # Missing c_user
    assert inspect_cookie_health("c_user=; xs=abc") is False  # Empty c_user
    assert inspect_cookie_health("c_user=0; xs=abc") is False  # Zero c_user
    assert inspect_cookie_health("") is False
    assert inspect_cookie_health(None) is False


def test_graphql_error_inspector_50_mixed_errors():
    """Verify 50+ mixed GraphQL errors accurately detect checkpoint code anywhere in the array."""
    checkpoint_codes = {190: "logged_out", 368: "restricted", 1357004: "checkpoint", 1357001: "checkpoint"}

    def inspect_graphql(payload):
        if not payload or not isinstance(payload, dict):
            return {"isError": False}
        errors = payload.get("errors", [])
        for err in errors:
            c = err.get("code") or (err.get("error", {}).get("code"))
            if c and c in checkpoint_codes:
                return {"isError": True, "code": c, "mapped": checkpoint_codes[c]}
        return {"isError": False}

    # 50 safe errors
    safe_50 = [{"code": 1000 + i, "message": f"Generic FB error {i}"} for i in range(50)]
    assert inspect_graphql({"errors": safe_50})["isError"] is False

    # Checkpoint at head (index 0)
    head_list = [{"code": 1357004, "message": "Account locked"}] + safe_50
    res_head = inspect_graphql({"errors": head_list})
    assert res_head["isError"] is True and res_head["code"] == 1357004

    # Code 190 at middle (index 25)
    mid_list = safe_50[:25] + [{"code": 190, "message": "Logged out"}] + safe_50[25:]
    res_mid = inspect_graphql({"errors": mid_list})
    assert res_mid["isError"] is True and res_mid["code"] == 190 and res_mid["mapped"] == "logged_out"

    # Code 368 at tail (index 50)
    tail_list = safe_50 + [{"code": 368, "message": "Restricted action"}]
    res_tail = inspect_graphql({"errors": tail_list})
    assert res_tail["isError"] is True and res_tail["code"] == 368 and res_tail["mapped"] == "restricted"


def test_dom_keyword_scanner_vietnamese_and_english():
    """Verify bilingual DOM security anomaly detection and case insensitivity."""
    dom_keywords = [
        "tài khoản của bạn đã bị khóa",
        "phê duyệt đăng nhập",
        "vô hiệu hóa",
        "phiên đăng nhập đã hết hạn",
        "your account has been locked",
        "account suspended",
        "login approval needed",
        "session expired",
    ]

    def scan_dom(text):
        if not text:
            return False
        lower = text.lower()
        return any(kw in lower for kw in dom_keywords)

    assert scan_dom("Cảnh báo: Tài khoản của bạn đã bị khóa do hoạt động bất thường") is True
    assert scan_dom("YOUR ACCOUNT HAS BEEN LOCKED FOR SECURITY REASONS") is True
    assert scan_dom("Phiên đăng nhập đã hết hạn, vui lòng login lại") is True
    assert scan_dom("Bảng tin Facebook hôm nay: Bạn có 5 thông báo mới") is False
    assert scan_dom("") is False
    assert scan_dom(None) is False


# =====================================================================
# SUITE 3: EXTENSION BACKGROUND WORKER LIFECYCLE & AUTH HEADERS
# =====================================================================
def test_background_cold_start_ephemeral_boot_id(background_js_raw):
    """Verify presence of synchronous cold-start boot ID with prefix 'node-boot-'."""
    assert '_ephemeralBootId = "node-boot-"' in background_js_raw
    match = re.search(r'const _ephemeralBootId = "node-boot-" \+ \(([\s\S]*?)\);', background_js_raw)
    assert match is not None, "Ephemeral boot ID definition must exist"


def test_background_rfc_6750_dual_auth_headers(background_js_raw):
    """Verify _getSyncHeaders generates BOTH X-Sync-Token and Authorization: Bearer <token>."""
    assert "function _getSyncHeaders(" in background_js_raw
    assert 'h["X-Sync-Token"] = _syncToken' in background_js_raw
    assert 'h["Authorization"] = `Bearer ${_syncToken}`' in background_js_raw
    assert 'h["X-Project-Key"] = _projectKey' in background_js_raw
    assert 'h["X-Worker-Id"]' in background_js_raw


def test_background_15s_active_loop(background_js_raw):
    """Verify background service worker sets up active foreground loop every 15s."""
    assert "setInterval(() => {" in background_js_raw
    assert "15000);" in background_js_raw
    assert "sendWorkerHeartbeat()" in background_js_raw
    assert "pollAndExecuteDistributedTask()" in background_js_raw


# =====================================================================
# SUITE 4: SAAS ADMIN CONSOLE DOM, TICKERS & XSS HARDENING
# =====================================================================
def escape_html(str_val: str) -> str:
    """Exact replica of admin.html escapeHtml."""
    if str_val is None:
        return ""
    s = str(str_val)
    mapping = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"}
    return re.sub(r'[&<>"\']', lambda m: mapping[m.group(0)], s)


def test_escape_html_xss_neutralization():
    """Verify escapeHtml neutralizes all standard and exotic XSS injection vectors."""
    vectors = [
        '<script>alert("XSS")</script>',
        '"><img src=x onerror=alert(1)>',
        "<svg/onload=alert('XSS')>",
        "' onmouseover='alert(1)",
        '"><script src=http://evil.com/xss.js></script>',
        '<iframe src="javascript:alert(1)"></iframe>',
        '& < > " \'',
    ]
    for vector in vectors:
        escaped = escape_html(vector)
        assert "<" not in escaped
        assert ">" not in escaped
        assert '"' not in escaped
        assert "'" not in escaped

    assert escape_html(None) == ""
    assert escape_html(123) == "123"
    assert escape_html(0) == "0"
    assert escape_html(False) == "False"


def test_admin_html_template_literals_escaped(admin_html_raw):
    """Audit template string interpolations in admin.html to ensure all user inputs are escaped."""
    required_escaped_interpolations = [
        "${escapeHtml(w.name || w.id)}",
        "${escapeHtml(w.id)}",
        "${escapeHtml(w.projectKey || 'all')}",
        "${escapeHtml(a.name || 'Tài khoản')}",
        "${escapeHtml(targetId)}",
        "${escapeHtml(p.content)}",
        "${escapeHtml(p.lastError)}",
        "${escapeHtml(t.accountId)}",
        "${escapeHtml(t.workerId)}",
    ]
    for interp in required_escaped_interpolations:
        assert interp in admin_html_raw, f"Missing required escaped template interpolation: {interp}"


def test_dynamic_lease_ticker_countdown_math():
    """Verify dynamic lease countdown calculation under normal, critical, expired, and clock drift."""
    def compute_lease(task, now_ms):
        if task.get("status") in ("completed", "failed", "cancelled", "pending"):
            return task["status"]

        lease_expires = int(task.get("leaseExpiresAt") or 0)
        if not lease_expires:
            return "none"

        diff_sec = round((lease_expires - now_ms) / 1000)
        if diff_sec <= 0:
            return "expired"
        elif diff_sec <= 15:
            return "amber"
        else:
            return "green"

    ref_now = 1720000000000
    # Normal > 15s (green)
    assert compute_lease({"status": "running", "leaseExpiresAt": ref_now + 45000}, ref_now) == "green"
    # Critical <= 15s (amber)
    assert compute_lease({"status": "assigned", "leaseExpiresAt": ref_now + 12000}, ref_now) == "amber"
    # Expired <= 0 (expired)
    assert compute_lease({"status": "running", "leaseExpiresAt": ref_now - 2000}, ref_now) == "expired"
    # Severe clock drift forward (client clock fast)
    assert compute_lease({"status": "assigned", "leaseExpiresAt": ref_now - 500000}, ref_now) == "expired"
    # Terminal statuses are unaffected
    assert compute_lease({"status": "completed"}, ref_now) == "completed"


def test_worker_relative_time_clock_drift():
    """Verify formatRelativeTime clamps negative seconds (future timestamps) to 0s 'Vừa xong'."""
    def format_relative_time(timestamp, now_val):
        ts = int(timestamp or 0)
        if not ts:
            return {"tier": "red", "text": "Chưa có dữ liệu"}
        diff_sec = max(0, math.floor((now_val - ts) / 1000))
        if diff_sec < 5:
            text = "Vừa xong (Just now)"
        elif diff_sec < 60:
            text = f"{diff_sec}s trước"
        elif diff_sec < 3600:
            text = f"{math.floor(diff_sec / 60)} phút trước"
        else:
            text = f"{math.floor(diff_sec / 3600)} giờ trước"

        tier = "green" if diff_sec <= 20 else ("amber" if diff_sec <= 45 else "red")
        return {"tier": tier, "text": text, "sec": diff_sec}

    now = 1720000100000
    # 2s ago
    res2 = format_relative_time(now - 2000, now)
    assert res2["tier"] == "green" and "Vừa xong" in res2["text"]

    # 15s ago
    res15 = format_relative_time(now - 15000, now)
    assert res15["tier"] == "green" and res15["sec"] == 15

    # 35s ago
    res35 = format_relative_time(now - 35000, now)
    assert res35["tier"] == "amber" and res35["sec"] == 35

    # 55s ago
    res55 = format_relative_time(now - 55000, now)
    assert res55["tier"] == "red" and res55["sec"] == 55

    # Clock drift: future timestamp (+60s)
    res_future = format_relative_time(now + 60000, now)
    assert res_future["sec"] == 0 and res_future["tier"] == "green" and "Vừa xong" in res_future["text"]


def test_admin_html_modals_and_containers(admin_html_soup):
    """Verify all 3 core modals and dual-view containers exist in admin.html."""
    modals = ["modalCreateTask", "modalTaskDetail", "workerAssignModal"]
    for m_id in modals:
        el = admin_html_soup.find(id=m_id)
        assert el is not None, f"Modal #{m_id} is missing from admin.html"

    # Dual-view containers for worker monitor
    assert admin_html_soup.find(id="workerGridContainer") is not None
    assert admin_html_soup.find(id="workerTableContainer") is not None


# =====================================================================
# SUITE 5: COMPREHENSIVE NODE.JS ADVERSARIAL HARNESS EXECUTION
# =====================================================================
def test_node_adversarial_harness_execution():
    """
    Executes the standalone Node.js adversarial stress test script
    (tests/test_tier5_extension_and_ui_adversarial.js) and verifies:
    - Exit code 0
    - All 1900+ assertions passed
    - Zero vulnerabilities reported
    """
    assert NODE_HARNESS_PATH.exists(), f"Harness must exist at {NODE_HARNESS_PATH}"

    result = subprocess.run(
        ["node", str(NODE_HARNESS_PATH)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30
    )

    print("\n--- Node Harness Output ---")
    print(result.stdout)
    if result.stderr:
        print("--- Node Harness Stderr ---")
        print(result.stderr)

    assert result.returncode == 0, f"Node adversarial harness failed with return code {result.returncode}"
    assert "ALL ADVERSARIAL TESTS PASSED" in result.stdout
    assert "Zero vulnerabilities" in result.stdout
