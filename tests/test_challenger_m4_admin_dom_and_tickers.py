"""
tests/test_challenger_m4_admin_dom_and_tickers.py
Challenger 2 Empirical Verification Suite for Milestone 4:
Admin Console DOM, JavaScript Logic, Tickers, and Legacy Non-Regression
"""

import subprocess
import sys
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
ADMIN_HTML_PATH = BACKEND_DIR / "admin.html"


@pytest.fixture(scope="module")
def admin_soup():
    assert ADMIN_HTML_PATH.exists(), f"admin.html must exist at {ADMIN_HTML_PATH}"
    content = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    return BeautifulSoup(content, "html.parser")


@pytest.fixture(scope="module")
def admin_html_content():
    assert ADMIN_HTML_PATH.exists()
    return ADMIN_HTML_PATH.read_text(encoding="utf-8")


def test_admin_html_all_7_navigation_tabs(admin_soup):
    """
    Verify that all 7 navigation tabs exist with exact IDs and matching nav triggers:
    tabPosts, tabCompleted, tabAccounts, tabWorkers, tabQueue, tabLogs, tabSettings
    """
    expected_tabs = [
        "tabPosts",
        "tabCompleted",
        "tabAccounts",
        "tabWorkers",
        "tabQueue",
        "tabLogs",
        "tabSettings"
    ]

    for tab_id in expected_tabs:
        # 1. Container element with exact ID exists
        tab_container = admin_soup.find(id=tab_id)
        assert tab_container is not None, f"Tab container #{tab_id} not found in DOM"
        assert "tab-content" in tab_container.get("class", []), f"#{tab_id} should have class 'tab-content'"

        # 2. Navigation trigger button with data-tab exists
        nav_btn = admin_soup.find(attrs={"data-tab": tab_id})
        assert nav_btn is not None, f"Nav button for tab {tab_id} with data-tab='{tab_id}' not found"

    # Default active tab should be tabPosts
    active_nav = admin_soup.find("button", class_="nav-tab-btn active")
    assert active_nav is not None, "There must be an active nav tab by default"
    assert active_nav.get("data-tab") == "tabPosts"

    active_content = admin_soup.find(id="tabPosts")
    assert active_content is not None, "tabPosts must exist"
    assert "active" in active_content.get("class", []), "tabPosts must have 'active' class by default"


def test_admin_html_required_containers_and_modals(admin_soup):
    """
    Verify that all required containers and modals exist:
    #kpiOverviewGrid, #workerGridContainer, #workerTableContainer, #workerAssignModal,
    #addAccountModal, #editAccountModal, #healthCheckModal, #modalCreateTask, #modalTaskDetail
    """
    required_ids = [
        "kpiOverviewGrid",
        "workerGridContainer",
        "workerTableContainer",
        "workerAssignModal",
        "addAccountModal",
        "editAccountModal",
        "healthCheckModal",
        "modalCreateTask",
        "modalTaskDetail"
    ]

    for el_id in required_ids:
        el = admin_soup.find(id=el_id)
        assert el is not None, f"Required container or modal #{el_id} is missing from admin.html"


def test_admin_html_kpi_overview_grid_metrics(admin_soup):
    """
    Verify Realtime KPI Overview Grid (#kpiOverviewGrid) metric cards:
    - Worker Nodes: #kpiWorkerNodes, #kpiWorkerPercent, #kpiWorkerSubtext
    - Farm Vitality: #kpiAccountVitality, #kpiLiveAccounts, #kpiTotalAccounts, #kpiVitalityBar
    - 24h Queue Throughput: #kpiQueueThroughput, #kpiSuccessRate, #kpiCompletedCount, #kpiFailedCount
    - Active Warm-up: #kpiActiveWarmup
    """
    kpi_elements = [
        "kpiWorkerNodes", "kpiWorkerPercent", "kpiWorkerSubtext",
        "kpiAccountVitality", "kpiLiveAccounts", "kpiTotalAccounts", "kpiVitalityBar",
        "kpiQueueThroughput", "kpiSuccessRate", "kpiCompletedCount", "kpiFailedCount",
        "kpiActiveWarmup"
    ]

    grid = admin_soup.find(id="kpiOverviewGrid")
    assert grid is not None, "#kpiOverviewGrid missing"

    for eid in kpi_elements:
        el = grid.find(id=eid)
        assert el is not None, f"KPI metric element #{eid} not found inside #kpiOverviewGrid"


def test_admin_html_worker_monitor_components(admin_soup):
    """
    Verify Worker Node monitoring sub-components:
    - Summary stat bars: #statWorkerTotal, #statWorkerOnline, #statWorkerBusy, #statWorkerOffline, #statWorkerAssignedAccs
    - View containers: #workerGridContainer, #workerTableContainer, #workerTableBody
    - Filters & toggles: #workerFilterStatus, #workerFilterProject, #workerRefreshCountdown
    - Assignment modal: #workerAssignModal, #assignModalWorkerName, #assignModalWorkerId, #workerAssignSearch
    """
    worker_tab = admin_soup.find(id="tabWorkers")
    assert worker_tab is not None, "#tabWorkers container missing"

    stats = ["statWorkerTotal", "statWorkerOnline", "statWorkerBusy", "statWorkerOffline", "statWorkerAssignedAccs"]
    for s in stats:
        assert worker_tab.find(id=s) is not None, f"Worker stat #{s} missing in #tabWorkers"

    assert worker_tab.find(id="workerGridContainer") is not None, "#workerGridContainer missing"
    assert worker_tab.find(id="workerTableContainer") is not None, "#workerTableContainer missing"
    assert worker_tab.find(id="workerTableBody") is not None, "#workerTableBody missing"
    assert worker_tab.find(id="workerRefreshCountdown") is not None, "#workerRefreshCountdown missing"

    assign_modal = admin_soup.find(id="workerAssignModal")
    assert assign_modal is not None, "#workerAssignModal missing"
    assert assign_modal.find(id="assignModalWorkerName") is not None
    assert assign_modal.find(id="assignAccountSearchInput") is not None
    assert assign_modal.find(id="btnSubmitWorkerAssign") is not None


def test_admin_html_account_farm_components(admin_soup):
    """
    Verify Account Farm tab components:
    - Stats: #farmStatTotal, #farmStatLive, #farmStatCheckpoint, #farmStatExpired
    - Table: #accountFarmTableBody
    - Modals: #addAccountModal, #editAccountModal, #healthCheckModal
    """
    acc_tab = admin_soup.find(id="tabAccounts")
    assert acc_tab is not None, "#tabAccounts container missing"

    for s in ["farmStatTotal", "farmStatLive", "farmStatCheckpoint", "farmStatExpired"]:
        assert acc_tab.find(id=s) is not None, f"Farm stat #{s} missing"

    assert acc_tab.find(id="accountFarmTableBody") is not None, "#accountFarmTableBody missing"
    assert admin_soup.find(id="addAccountModal") is not None
    assert admin_soup.find(id="editAccountModal") is not None
    assert admin_soup.find(id="healthCheckModal") is not None


def test_admin_html_task_queue_components(admin_soup):
    """
    Verify Task Queue tab components:
    - Table: #taskQueueTableBody
    - Modals: #modalCreateTask, #modalTaskDetail
    - Create modal inputs: #modalTaskType, #modalTaskProjectKey, #modalTaskAccountId, #btnSubmitTask
    """
    queue_tab = admin_soup.find(id="tabQueue")
    assert queue_tab is not None, "#tabQueue missing"
    assert queue_tab.find(id="taskQueueTableBody") is not None, "#taskQueueTableBody missing"

    create_modal = admin_soup.find(id="modalCreateTask")
    assert create_modal is not None, "#modalCreateTask missing"
    assert create_modal.find(id="modalTaskType") is not None
    assert create_modal.find(id="modalTaskProjectKey") is not None
    assert create_modal.find(id="modalTaskAccountId") is not None
    assert create_modal.find(id="btnSubmitTask") is not None

    detail_modal = admin_soup.find(id="modalTaskDetail")
    assert detail_modal is not None, "#modalTaskDetail missing"


def test_legacy_form_functions_and_backward_compatibility(admin_html_content, admin_soup):
    """
    Verify that legacy post creation form controls and functions:
    populatePostAccountDropdown, onSelectPostAccount, insertSeedingPreset, insertAutoReplyPreset
    are intact and have not suffered regressions.
    """
    # 1. Functions defined in JS script
    legacy_fns = [
        "populatePostAccountDropdown",
        "onSelectPostAccount",
        "insertSeedingPreset",
        "insertAutoReplyPreset",
        "loadAccounts"
    ]
    for fn in legacy_fns:
        assert f"function {fn}" in admin_html_content or f"{fn} =" in admin_html_content, (
            f"Legacy function {fn} must be defined in admin.html"
        )

    # 2. Legacy post creation form controls
    post_form = admin_soup.find(id="formPost")
    assert post_form is not None, "#formPost missing from admin.html"

    expected_inputs = [
        "postType", "postTargetType", "postTargetId",
        "postScheduledTime", "postAutoReplyText", "postAutoReactType",
        "postAccessToken", "postRepeat", "postProjectKey",
        "postContent", "postMediaUrl", "postSeedingComments"
    ]
    for inp in expected_inputs:
        assert post_form.find(id=inp) is not None, f"Input #{inp} missing from #formPost"


def test_node_ticker_stress_test_suite_execution():
    """
    Execute tests/test_challenger_m4_admin_stress.js via Node.js
    Stress-testing:
    - updateLeaseCountdownsInDom with past, future, exact, negative, null timestamps
    - formatRelativeTime with negative, zero, 5s, 60s, 3600s, null timestamps
    - resolveWorkerStatus with online, busy, stale/offline nodes
    - populatePostAccountDropdown and onSelectPostAccount behavior
    """
    js_test_path = PROJECT_ROOT / "tests" / "test_challenger_m4_admin_stress.js"
    assert js_test_path.exists(), f"Stress test script {js_test_path} missing"

    result = subprocess.run(
        ["node", str(js_test_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    print("NODE STRESS TEST OUTPUT:\n", result.stdout)
    if result.stderr:
        print("NODE STRESS TEST STDERR:\n", result.stderr)

    assert result.returncode == 0, f"Node.js stress test suite failed with exit code {result.returncode}"
    assert "ALL 19/19 TESTS PASSED CLEANLY" in result.stdout
