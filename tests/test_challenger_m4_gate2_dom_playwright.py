"""
tests/test_challenger_m4_gate2_dom_playwright.py
Challenger 2 Empirical Verification:
Headless Browser DOM Visibility, Tab Switching, and formatRelativeTime Edge-Case Stress Testing
"""

import re
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_HTML_PATH = PROJECT_ROOT / "fbauto-backend-python" / "admin.html"

ALL_TABS = [
    "tabPosts",
    "tabCompleted",
    "tabAccounts",
    "tabWorkers",
    "tabQueue",
    "tabLogs",
    "tabSettings"
]


def test_no_inline_display_none_on_tab_content():
    """
    Verify that no .tab-content element carries inline style="display:none;".
    Checks both parsed DOM elements and raw HTML regex patterns.
    """
    assert ADMIN_HTML_PATH.exists(), f"admin.html not found at {ADMIN_HTML_PATH}"
    content = ADMIN_HTML_PATH.read_text(encoding="utf-8")

    # 1. BeautifulSoup verification
    soup = BeautifulSoup(content, "html.parser")
    tab_contents = soup.find_all(class_=re.compile(r"\btab-content\b"))
    assert len(tab_contents) >= 7, f"Expected at least 7 .tab-content elements, found {len(tab_contents)}"

    for el in tab_contents:
        style = el.get("style", "")
        # Normalise whitespace
        norm_style = re.sub(r"\s+", "", style.lower())
        assert "display:none" not in norm_style, (
            f"Element #{el.get('id', 'unknown')} has inline display:none in style attribute: '{style}'"
        )

    # 2. Regex verification on raw markup for defense-in-depth
    raw_matches = re.findall(
        r'<div[^>]*class=["\'][^"\']*\btab-content\b[^"\']*["\'][^>]*style=["\'][^"\']*display\s*:\s*none',
        content,
        re.IGNORECASE
    )
    assert len(raw_matches) == 0, f"Found raw inline display:none on tab-content: {raw_matches}"


def test_playwright_tab_switching_and_visibility():
    """
    Empirically verify using headless Chromium that clicking each of the 7 tabs:
    - Sets active tab to visible=True
    - Sets active tab computed display to 'block' (or 'grid' for tabPosts)
    - Sets all inactive tabs to visible=False and computed display to 'none'
    """
    file_url = ADMIN_HTML_PATH.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_load_state("domcontentloaded")

        # Initial default state: tabPosts must be active
        init_active = page.evaluate("""() => {
            const el = document.getElementById('tabPosts');
            const style = window.getComputedStyle(el);
            return {
                classes: el.className,
                display: style.display,
                hasActive: el.classList.contains('active')
            };
        }""")
        assert init_active["hasActive"] is True, "tabPosts must have 'active' class initially"
        assert init_active["display"] == "grid", f"tabPosts should have display: grid, got {init_active['display']}"
        assert page.locator("#tabPosts").is_visible() is True

        # Initial check that other 6 tabs are completely hidden
        for other_id in ALL_TABS:
            if other_id == "tabPosts":
                continue
            is_vis = page.locator(f"#{other_id}").is_visible()
            comp_display = page.evaluate(f"() => window.getComputedStyle(document.getElementById('{other_id}')).display")
            assert is_vis is False, f"Inactive tab #{other_id} should not be visible initially"
            assert comp_display == "none", f"Inactive tab #{other_id} should have display: none, got {comp_display}"

        # Sequentially click all 7 tabs and verify visibility transitions
        for tab_id in ALL_TABS:
            btn = page.locator(f"button.nav-tab-btn[data-tab='{tab_id}']")
            assert btn.count() > 0, f"Nav button for {tab_id} not found"
            btn.click()

            # Target tab assertions
            target_el = page.locator(f"#{tab_id}")
            assert target_el.is_visible() is True, f"Tab #{tab_id} must be visible after click"

            target_info = page.evaluate(f"""() => {{
                const el = document.getElementById('{tab_id}');
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return {{
                    classes: el.className,
                    display: style.display,
                    width: rect.width,
                    height: rect.height
                }};
            }}""")

            expected_display = "grid" if tab_id == "tabPosts" else "block"
            assert target_info["display"] == expected_display, (
                f"Tab #{tab_id} expected display '{expected_display}', got '{target_info['display']}'"
            )
            assert target_info["width"] > 0, f"Tab #{tab_id} rendered width should be > 0"
            assert target_info["height"] > 0, f"Tab #{tab_id} rendered height should be > 0"

            # All other tabs assertions: strictly hidden
            for other_id in ALL_TABS:
                if other_id == tab_id:
                    continue
                other_vis = page.locator(f"#{other_id}").is_visible()
                other_disp = page.evaluate(f"() => window.getComputedStyle(document.getElementById('{other_id}')).display")
                assert other_vis is False, f"Inactive tab #{other_id} must be hidden when #{tab_id} is active"
                assert other_disp == "none", f"Inactive tab #{other_id} must have display: none when #{tab_id} is active"

        browser.close()


def test_playwright_rapid_adversarial_tab_cycling():
    """
    Stress-test rapid, non-sequential tab switching (back-and-forth and jumping)
    to confirm DOM classList mutations never get out of sync or leave multiple tabs visible.
    """
    file_url = ADMIN_HTML_PATH.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_load_state("domcontentloaded")

        # Adversarial sequence jumping across categories
        sequence = [
            "tabQueue", "tabPosts", "tabWorkers", "tabCompleted",
            "tabSettings", "tabAccounts", "tabLogs", "tabQueue",
            "tabSettings", "tabPosts"
        ]

        for step_idx, tab_id in enumerate(sequence):
            page.locator(f"button.nav-tab-btn[data-tab='{tab_id}']").click()

            # Verify that EXACTLY 1 tab-content element is active and visible
            stats = page.evaluate("""() => {
                const tabs = Array.from(document.querySelectorAll('.tab-content'));
                const visibleCount = tabs.filter(t => window.getComputedStyle(t).display !== 'none').length;
                const activeClassCount = tabs.filter(t => t.classList.contains('active')).length;
                const activeId = tabs.find(t => t.classList.contains('active'))?.id || null;
                return { visibleCount, activeClassCount, activeId };
            }""")

            assert stats["activeClassCount"] == 1, (
                f"Step {step_idx}: expected exactly 1 tab with .active, found {stats['activeClassCount']}"
            )
            assert stats["visibleCount"] == 1, (
                f"Step {step_idx}: expected exactly 1 visible tab, found {stats['visibleCount']}"
            )
            assert stats["activeId"] == tab_id, (
                f"Step {step_idx}: expected active tab #{tab_id}, found #{stats['activeId']}"
            )

        browser.close()


def test_format_relative_time_adversarial_edge_cases():
    """
    Empirically execute window.formatRelativeTime in real browser runtime across
    comprehensive adversarial edge cases:
    - null, undefined, "invalid", "", -100, 0, Date.now(), future, NaN, Infinity, objects.
    Verify that:
    1. NEVER produces "NaN ngày trước" or any string containing "NaN".
    2. Always returns an object with text (string), tier ('green'|'amber'|'red'), and sec (number).
    """
    file_url = ADMIN_HTML_PATH.as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_load_state("domcontentloaded")

        test_inputs = [
            (None, "null"),
            ("undefined", "undefined"),
            ("invalid", "invalid string"),
            ("NaN", "NaN string"),
            ("-100", "negative string"),
            (-100, "negative number"),
            (0, "zero number"),
            ("0", "zero string"),
            ("", "empty string"),
            ("   ", "whitespace string"),
            (9999999999999, "far future"),
            (-9999999999999, "far past negative"),
        ]

        results = page.evaluate("""() => {
            const edgeCases = [
                { input: null, label: 'null' },
                { input: undefined, label: 'undefined' },
                { input: 'invalid', label: 'invalid string' },
                { input: NaN, label: 'NaN' },
                { input: -100, label: 'negative -100' },
                { input: 0, label: 'zero' },
                { input: '', label: 'empty string' },
                { input: '   ', label: 'whitespace' },
                { input: {}, label: 'empty object' },
                { input: [], label: 'empty array' },
                { input: Infinity, label: 'Infinity' },
                { input: -Infinity, label: '-Infinity' },
                { input: Date.now(), label: 'Date.now()' },
                { input: Date.now() + 60000, label: 'Future 60s' },
                { input: Date.now() - 3000, label: 'Past 3s' },
                { input: Date.now() - 30000, label: 'Past 30s' },
                { input: Date.now() - 300000, label: 'Past 5 min' },
                { input: Date.now() - 7200000, label: 'Past 2 hours' },
                { input: Date.now() - 172800000, label: 'Past 2 days' }
            ];

            return edgeCases.map(tc => {
                const res = window.formatRelativeTime(tc.input);
                return {
                    label: tc.label,
                    text: res ? res.text : null,
                    tier: res ? res.tier : null,
                    sec: res ? res.sec : null,
                    hasNaN: res && typeof res.text === 'string' ? res.text.includes('NaN') : false,
                    isObject: typeof res === 'object' && res !== null
                };
            });
        }""")

        for r in results:
            label = r["label"]
            assert r["isObject"] is True, f"formatRelativeTime({label}) did not return an object"
            assert isinstance(r["text"], str) and len(r["text"]) > 0, f"formatRelativeTime({label}) text empty"
            assert r["hasNaN"] is False, f"formatRelativeTime({label}) contained 'NaN'! Text: '{r['text']}'"
            assert r["tier"] in ["green", "amber", "red"], f"formatRelativeTime({label}) invalid tier: {r['tier']}"
            assert isinstance(r["sec"], (int, float)), f"formatRelativeTime({label}) sec is not numeric: {r['sec']}"
            assert not (r["sec"] != r["sec"]), f"formatRelativeTime({label}) sec is NaN"

        # Verify specific expected behavior
        null_res = page.evaluate("() => window.formatRelativeTime(null)")
        assert null_res["text"] == "Chưa có dữ liệu"
        assert null_res["tier"] == "red"

        invalid_res = page.evaluate("() => window.formatRelativeTime('invalid_timestamp')")
        assert invalid_res["text"] == "Chưa có dữ liệu"
        assert invalid_res["tier"] == "red"

        neg_res = page.evaluate("() => window.formatRelativeTime(-100)")
        assert neg_res["text"] == "Chưa có dữ liệu"
        assert neg_res["tier"] == "red"

        zero_res = page.evaluate("() => window.formatRelativeTime(0)")
        assert zero_res["text"] == "Chưa có dữ liệu"
        assert zero_res["tier"] == "red"

        now_res = page.evaluate("() => window.formatRelativeTime(Date.now())")
        assert "Vừa xong" in now_res["text"]
        assert now_res["tier"] == "green"
        assert now_res["sec"] == 0

        future_res = page.evaluate("() => window.formatRelativeTime(Date.now() + 10000)")
        assert "Vừa xong" in future_res["text"]
        assert future_res["tier"] == "green"
        assert future_res["sec"] == 0

        browser.close()
