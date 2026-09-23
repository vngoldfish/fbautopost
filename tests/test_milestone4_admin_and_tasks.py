"""
tests/test_milestone4_admin_and_tasks.py
Integration & Verification Suite for Milestone 4 (Production SaaS Admin Console & Tasks)
Covers:
1. POST /api/tasks/{task_id}/cancel endpoint behavior (pending, assigned/running, completed, not found)
2. Activity log auditing for CANCEL_TASK events
3. Worker release and status reset from 'busy' to 'online' on task cancellation
4. Rejection of lease extension (heartbeat) on cancelled tasks (HTTP 400)
5. Admin Console (admin.html) structural integrity and CSS inline display:none guard
"""

import sys
import re
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "fbauto-backend-python"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.core.config import settings

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_TOKEN", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    test_client = TestClient(app)
    test_client.headers["X-Project-Key"] = "default"
    return test_client


def test_cancel_nonexistent_task(client):
    """Cancelling a non-existent task returns 404 Not Found."""
    res = client.post("/api/tasks/nonexistent_task_99999/cancel")
    assert res.status_code == 404
    data = res.json()
    assert "not found" in data.get("detail", "").lower()


def test_cancel_pending_task(client):
    """Cancelling a pending task transitions status to cancelled and clears lease."""
    # 1. Create a pending task
    create_res = client.post("/api/tasks", json={
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 5,
        "payload": {"duration": 60}
    })
    assert create_res.status_code == 201
    task_id = create_res.json()["task"]["id"]

    # 2. Cancel the task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data.get("success") is True
    assert cancel_data.get("status") == "cancelled"
    assert cancel_data.get("taskId") == task_id

    # 3. Verify task status in database via taskId filter
    get_res = client.get(f"/api/tasks?taskId={task_id}")
    assert get_res.status_code == 200
    tasks = get_res.json().get("tasks", [])
    assert len(tasks) == 1, f"Expected 1 task for taskId={task_id}, got {len(tasks)}"
    cancelled_task = tasks[0]
    assert cancelled_task["id"] == task_id
    assert cancelled_task["status"] == "cancelled"
    assert cancelled_task["leaseExpiresAt"] is None

    # Also verify default list endpoint includes recent tasks via created_at DESC ordering
    list_res = client.get("/api/tasks?limit=50")
    assert list_res.status_code == 200
    recent_tasks = list_res.json().get("tasks", [])
    found_in_recent = next((t for t in recent_tasks if t["id"] == task_id), None)
    assert found_in_recent is not None, f"Task {task_id} missing from recent tasks (check created_at DESC sort order)"
    assert found_in_recent["status"] == "cancelled"

    # 4. Verify CANCEL_TASK activity log exists
    logs_res = client.get("/api/logs?limit=50")
    assert logs_res.status_code == 200
    logs = logs_res.json().get("logs", [])
    cancel_log = next((l for l in logs if l.get("action") == "CANCEL_TASK" and l.get("details", {}).get("taskId") == task_id), None)
    assert cancel_log is not None
    assert cancel_log.get("action") == "CANCEL_TASK"


def test_cancel_running_task_releases_worker(client):
    """Cancelling an active task releases worker's current_task_id lock."""
    # 1. Register a worker
    worker_id = "m4_worker_test_cancel_node"
    client.post("/api/workers/register", json={
        "id": worker_id,
        "name": "M4 Test Worker",
        "projectKey": "default"
    })

    # 2. Create a task and poll it with worker
    create_res = client.post("/api/tasks", json={
        "taskType": "post",
        "projectKey": "default",
        "priority": 10,
        "payload": {"content": "Test cancel release"}
    })
    task_id = create_res.json()["task"]["id"]

    # Worker claims task via poll
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["post"]
    })
    assert poll_res.status_code == 200, f"Poll failed: {poll_res.text}"
    claimed_task = poll_res.json().get("task")
    assert claimed_task is not None
    claimed_id = claimed_task["id"]

    # 3. Cancel the task
    cancel_res = client.post(f"/api/tasks/{claimed_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json().get("success") is True

    # 4. Verify worker current_task_id is cleared
    workers_res = client.get("/api/workers")
    assert workers_res.status_code == 200
    workers = workers_res.json().get("workers", [])
    w = next((x for x in workers if x["id"] == worker_id), None)
    assert w is not None
    assert w.get("currentTaskId") is None


def test_cancel_completed_task_rejected(client):
    """Completed tasks cannot be cancelled."""
    # 1. Create and complete a task
    create_res = client.post("/api/tasks", json={
        "taskType": "seed",
        "projectKey": "default",
        "payload": {"targetUrl": "https://fb.com/test"}
    })
    task_id = create_res.json()["task"]["id"]

    # Complete it via status endpoint
    client.post(f"/api/tasks/{task_id}/status", json={
        "status": "completed",
        "result": {"status": "ok"}
    })

    # 2. Try cancelling completed task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    data = cancel_res.json()
    assert data.get("success") is False
    assert data.get("status") == "completed"


def test_admin_console_html_structure():
    """Verify that admin.html contains all 7 tabs, KPI components, and modals."""
    admin_path = BACKEND_DIR / "admin.html"
    assert admin_path.exists(), "admin.html must exist"

    content = admin_path.read_text(encoding="utf-8")

    # All Tabs present in navigation (including separated Create Post, Pending Posts, and Projects tabs)
    tabs = ["tabCreatePost", "tabPendingPosts", "tabCompleted", "tabProjects", "tabAccounts", "tabWorkers", "tabQueue", "tabLogs", "tabSettings"]
    for t in tabs:
        assert f'data-tab="{t}"' in content, f"Nav tab button data-tab='{t}' must exist"
        assert f'id="{t}"' in content, f"Tab container id='{t}' must exist"

    # 2. Top KPI Analytics Overview Grid
    kpi_ids = ["kpiOverviewGrid", "kpiWorkerNodes", "kpiAccountVitality", "kpiQueueThroughput", "kpiActiveWarmup"]
    for k in kpi_ids:
        assert f'id="{k}"' in content, f"KPI element id='{k}' must exist"

    # 3. All Milestone 4 Modals
    modals = ["workerAssignModal", "addAccountModal", "editAccountModal", "healthCheckModal", "modalCreateTask", "modalTaskDetail"]
    for m in modals:
        assert f'id="{m}"' in content, f"Modal id='{m}' must exist"

    # 4. Key JavaScript Controller Functions
    js_funcs = [
        "loadWorkerNodes", "resolveWorkerStatus", "renderWorkerNodes", "setWorkerViewMode",
        "openWorkerAssignModal", "submitWorkerAssignment", "deleteWorkerNode",
        "loadAccountFarm", "loadAccounts", "updateFarmKpiCounters", "applyFarmFilters",
        "renderAccountFarmTable", "openAddAccountModal", "submitAddAccountModal",
        "openEditAccountModal", "submitEditAccountModal", "openHealthCheckModal", "triggerAccountHealth",
        "loadTasks", "computeLeaseBadgeHtml", "updateLeaseCountdownsInDom", "triggerCancelTask",
        "openCreateTaskModal", "handleCreateTaskSubmit", "openTaskDetailModal",
        "loadKpiMetrics", "loadLogs", "setLogLevelFilter", "toggleLogAutoScroll", "renderEnhancedLogs"
    ]
    for fn in js_funcs:
        assert f"function {fn}" in content or f"{fn} =" in content or f"async function {fn}" in content, f"JS function {fn} must be defined"


def test_tab_containers_no_inline_display_none():
    """
    Verify that Milestone 4 tab containers (#tabAccounts, #tabWorkers, #tabQueue, #tabLogs)
    do NOT have inline style="display:none;" which conflicts with CSS specificity (1,0,0,0 vs 0,0,2,0),
    and verify that .tab-content.active enforces display: block !important.
    """
    admin_path = BACKEND_DIR / "admin.html"
    assert admin_path.exists(), "admin.html must exist"

    content = admin_path.read_text(encoding="utf-8")

    # 1. Verify tab containers do NOT contain inline style="display:none;"
    tab_ids = ["tabAccounts", "tabWorkers", "tabQueue", "tabLogs"]
    for tid in tab_ids:
        pattern = rf'<div[^>]*id=["\']{tid}["\'][^>]*>'
        match = re.search(pattern, content)
        assert match is not None, f"Tab container div #{tid} not found in admin.html"
        tag_str = match.group(0)
        normalized_tag = tag_str.lower().replace(" ", "").replace('"', "'")
        assert "display:none" not in normalized_tag, (
            f"Container #{tid} must NOT have inline style='display:none;' - found: {tag_str}"
        )

    # 2. Verify .tab-content.active rule in <style> has !important
    assert re.search(r'\.tab-content\.active\s*\{[^}]*display\s*:\s*block\s*!important', content), (
        "admin.html stylesheet must define '.tab-content.active { display: block !important; }'"
    )


def test_extend_lease_rejected_on_cancelled_task(client):
    """
    Verify that calling POST /api/tasks/{task_id}/heartbeat on a cancelled task
    returns HTTP 400 Bad Request to prevent resurrecting cancelled task leases.
    """
    # 1. Create a task
    create_res = client.post("/api/tasks", json={
        "taskType": "warmup",
        "projectKey": "default",
        "priority": 5,
        "payload": {"duration": 60}
    })
    assert create_res.status_code == 201
    task_id = create_res.json()["task"]["id"]

    # 2. Cancel the task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # 3. Call extend lease / heartbeat on the cancelled task
    hb_res = client.post(f"/api/tasks/{task_id}/heartbeat", json={"extendSec": 60})
    assert hb_res.status_code == 400, (
        f"Expected HTTP 400 when heartbeating on a cancelled task, got {hb_res.status_code}: {hb_res.text}"
    )
    detail = hb_res.json().get("detail", "").lower()
    assert "cannot extend lease" in detail or "cancelled" in detail, (
        f"Expected descriptive error detail, got: {hb_res.json()}"
    )


def test_cancel_task_resets_busy_worker_status(client):
    """
    Verify that cancelling a running task resets a busy worker's status to 'online'
    and clears worker's currentTaskId.
    """
    now_ts = int(time.time() * 1000)
    worker_id = f"m4_worker_busy_reset_{now_ts}"

    # 1. Register a worker
    reg_res = client.post("/api/workers/register", json={
        "id": worker_id,
        "name": "Busy Reset Worker",
        "projectKey": "default"
    })
    assert reg_res.status_code == 200

    # 2. Create task with high priority so poll claims it immediately
    create_res = client.post("/api/tasks", json={
        "taskType": "post",
        "projectKey": "default",
        "priority": 99999,
        "payload": {"content": "Busy worker reset test"}
    })
    assert create_res.status_code == 201
    task_id = create_res.json()["task"]["id"]

    # 3. Worker claims task via poll
    poll_res = client.post("/api/tasks/poll", json={
        "workerId": worker_id,
        "projectKey": "default",
        "supportedTypes": ["post"]
    })
    assert poll_res.status_code == 200
    claimed = poll_res.json().get("task")
    assert claimed is not None
    assert claimed["id"] == task_id

    # 4. Worker reports running status -> updates worker status to 'busy'
    status_res = client.post(f"/api/tasks/{task_id}/status", json={
        "workerId": worker_id,
        "status": "running"
    })
    assert status_res.status_code == 200

    # Verify worker is busy in GET /api/workers
    workers_res1 = client.get("/api/workers")
    assert workers_res1.status_code == 200
    workers1 = workers_res1.json().get("workers", [])
    w_busy = next((w for w in workers1 if w["id"] == worker_id), None)
    assert w_busy is not None
    assert w_busy["status"] == "busy"
    assert w_busy["currentTaskId"] == task_id

    # 5. Cancel the task
    cancel_res = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True

    # 6. Verify worker status is reset to 'online' and currentTaskId is cleared
    workers_res2 = client.get("/api/workers")
    assert workers_res2.status_code == 200
    workers2 = workers_res2.json().get("workers", [])
    w_online = next((w for w in workers2 if w["id"] == worker_id), None)
    assert w_online is not None
    assert w_online["status"] == "online", (
        f"Worker status should be reset to 'online', got: '{w_online['status']}'"
    )
    assert w_online["currentTaskId"] is None, (
        f"Worker currentTaskId should be None, got: {w_online['currentTaskId']}"
    )
