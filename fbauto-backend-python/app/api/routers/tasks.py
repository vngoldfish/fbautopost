"""
app/api/routers/tasks.py
APIRouter for Distributed Task Queue Engine:
Task creation, atomic polling with 60s lease locking, and status reporting.
Prepares task queue execution for Milestone 2.
"""

import time
import json
import random
import string
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException, status
from app.db.session import query_all, query_one, execute_write, transaction, add_activity_log
from app.core.security import extract_project_key
from app.models.task import TaskPollRequest, TaskStatusUpdateRequest, TaskCreateRequest

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

def format_task(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None

    payload = {}
    if row.get("payload"):
        try:
            payload = json.loads(row["payload"])
        except Exception:
            pass

    result_data = {}
    if row.get("result_data"):
        try:
            result_data = json.loads(row["result_data"])
        except Exception:
            pass

    return {
        "id": row.get("id"),
        "type": row.get("task_type"),
        "projectKey": row.get("project_key") or "all",
        "workerId": row.get("worker_id"),
        "accountId": row.get("account_id"),
        "postId": row.get("post_id"),
        "priority": row.get("priority") or 0,
        "status": row.get("status") or "pending",
        "payload": payload,
        "scheduledTime": row.get("scheduled_time"),
        "claimedAt": row.get("claimed_at"),
        "leaseExpiresAt": row.get("lease_expires_at"),
        "completedAt": row.get("completed_at"),
        "retryCount": row.get("retry_count") or 0,
        "maxRetries": row.get("max_retries") or 3,
        "lastError": row.get("last_error"),
        "result": result_data,
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at")
    }

@router.get("")
def list_tasks(
    status: Optional[str] = None,
    projectKey: Optional[str] = None,
    workerId: Optional[str] = None,
    taskId: Optional[str] = None,
    id: Optional[str] = None,
    limit: int = 100
):
    """Lists queued tasks with optional filtering and chronological ordering."""
    sql = "SELECT * FROM tasks WHERE 1=1"
    params = []

    if status and status != "all":
        sql += " AND status = ?"
        params.append(status)

    if projectKey and projectKey != "all":
        sql += " AND (project_key = ? OR project_key = 'all')"
        params.append(projectKey)

    if workerId:
        sql += " AND worker_id = ?"
        params.append(workerId)

    target_task_id = (taskId or id or "").strip()
    if target_task_id:
        sql += " AND id = ?"
        params.append(target_task_id)

    sql += " ORDER BY created_at DESC, priority DESC LIMIT ?"
    params.append(limit)

    rows = query_all(sql, tuple(params))
    tasks = [format_task(r) for r in rows]
    return {"tasks": tasks, "total": len(tasks)}

@router.get("/{task_id}")
def get_task(task_id: str):
    """Retrieves a single task by its unique ID."""
    row = query_one("SELECT * FROM tasks WHERE id = ?", (task_id.strip(),))
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": format_task(row)}


@router.post("/poll")
def poll_task(request: Request, payload: TaskPollRequest):
    """
    Atomically claims the highest priority pending task eligible for the requesting worker node.
    Enforces 60-second lease expiration to prevent worker crashes from permanently stalling tasks.
    Excludes tasks for checkpointed/expired accounts and respects project partitioning & account affinity.
    """
    worker_id = payload.workerId.strip()

    # Priority for projectKey: explicit non-empty body param > header > 'all'
    if payload.projectKey and payload.projectKey.strip():
        project_key = payload.projectKey.strip()
    else:
        project_key = extract_project_key(request) or "all"

    supported_types = payload.supportedTypes or ["post", "seed", "warmup", "reply_comment"]
    now_ms = int(time.time() * 1000)
    lease_duration_ms = 60000  # 60 seconds lease

    with transaction() as conn:
        # Check if worker has assigned accounts
        w_cur = conn.execute("SELECT assigned_accounts FROM workers WHERE id = ?", (worker_id,))
        w_row = w_cur.fetchone()
        assigned_accs = []
        if w_row and w_row["assigned_accounts"]:
            try:
                assigned_accs = json.loads(w_row["assigned_accounts"])
            except Exception:
                pass

        type_placeholders = ", ".join(["?"] * len(supported_types))

        # Build project key filter
        if project_key != "all":
            sql_pk = "AND project_key = ?"
            pk_params = [project_key]
        else:
            sql_pk = ""
            pk_params = []

        # Account affinity filter
        affinity_sql = ""
        affinity_params = []
        if assigned_accs:
            acc_placeholders = ", ".join(["?"] * len(assigned_accs))
            affinity_sql = f"""
                AND (
                    account_id IS NULL
                    OR account_id IN ({acc_placeholders})
                    OR account_id IN (SELECT id FROM accounts WHERE target_id IN ({acc_placeholders}))
                    OR account_id IN (SELECT target_id FROM accounts WHERE id IN ({acc_placeholders}))
                )
            """
            affinity_params = assigned_accs + assigned_accs + assigned_accs
        else:
            affinity_sql = """
                AND (
                    account_id IS NULL
                    OR account_id NOT IN (
                        SELECT id FROM accounts WHERE worker_id IS NOT NULL AND worker_id != ?
                        UNION
                        SELECT target_id FROM accounts WHERE worker_id IS NOT NULL AND worker_id != ?
                    )
                )
            """
            affinity_params = [worker_id, worker_id]

        sql = f"""
            SELECT * FROM tasks
            WHERE (
                (status = 'pending' AND (worker_id = ? OR worker_id IS NULL))
                OR
                (status IN ('assigned', 'running') AND lease_expires_at < ?)
            )
              {sql_pk}
              AND task_type IN ({type_placeholders})
              AND scheduled_time <= ?
              AND (
                  account_id IS NULL OR account_id NOT IN (
                      SELECT id FROM accounts WHERE status IN ('checkpoint', 'expired', 'logged_out')
                      UNION
                      SELECT target_id FROM accounts WHERE status IN ('checkpoint', 'expired', 'logged_out')
                  )
              )
              {affinity_sql}
            ORDER BY priority DESC, scheduled_time ASC
            LIMIT 1
        """
        params = [worker_id, now_ms] + pk_params + supported_types + [now_ms] + affinity_params
        cur = conn.execute(sql, tuple(params))
        row = cur.fetchone()

        if not row:
            return {"task": None}

        task_id = row["id"]
        lease_expires = now_ms + lease_duration_ms

        # Ensure worker exists in workers table
        conn.execute("""
            INSERT INTO workers (id, name, project_key, status, last_heartbeat, created_at, updated_at)
            VALUES (?, ?, ?, 'online', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = 'online',
                last_heartbeat = excluded.last_heartbeat,
                updated_at = excluded.updated_at
        """, (worker_id, f"Node-{worker_id[-6:]}", project_key, now_ms, now_ms, now_ms))

        conn.execute("""
            UPDATE tasks
            SET status = 'assigned', worker_id = ?, claimed_at = ?,
                lease_expires_at = ?, updated_at = ?
            WHERE id = ?
        """, (worker_id, now_ms, lease_expires, now_ms, task_id))

        # Re-fetch updated row
        cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        updated_row = dict(cur.fetchone())

    add_activity_log(
        "CLAIM_TASK",
        entity_type="task",
        entity_id=task_id,
        project_key=project_key,
        details={"workerId": worker_id, "taskId": task_id, "type": updated_row.get("task_type")}
    )

    return {"task": format_task(updated_row)}

@router.post("/{task_id}/status")
def update_task_status(task_id: str, payload: TaskStatusUpdateRequest):
    """Worker node reports execution completion, progress, or failure for a task."""
    existing = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    now_ms = int(time.time() * 1000)
    raw_status = payload.status

    if raw_status == "failed":
        curr_retries = (existing.get("retry_count") or 0) + 1
        max_retries = existing.get("max_retries", 3)
        if max_retries is None:
            max_retries = 3

        if curr_retries < max_retries:
            next_status = "pending"
            worker_id_val = None
            lease_val = None
        else:
            next_status = "failed"
            worker_id_val = payload.workerId
            lease_val = None

        execute_write("""
            UPDATE tasks
            SET status = ?, worker_id = ?, lease_expires_at = ?,
                retry_count = ?, last_error = ?, updated_at = ?
            WHERE id = ?
        """, (next_status, worker_id_val, lease_val, curr_retries, payload.error, now_ms, task_id))

        if payload.workerId:
            execute_write(
                "UPDATE workers SET current_task_id = NULL WHERE id = ? AND current_task_id = ?",
                (payload.workerId, task_id)
            )

    elif raw_status == "completed":
        result_json = json.dumps(payload.result or {}, ensure_ascii=False)
        execute_write("""
            UPDATE tasks
            SET status = 'completed', completed_at = ?, result_data = ?,
                lease_expires_at = NULL, updated_at = ?
            WHERE id = ?
        """, (now_ms, result_json, now_ms, task_id))

        if payload.workerId:
            execute_write(
                "UPDATE workers SET current_task_id = NULL WHERE id = ? AND current_task_id = ?",
                (payload.workerId, task_id)
            )

    elif raw_status == "running":
        result_json = json.dumps(payload.result or {}, ensure_ascii=False) if payload.result else None
        execute_write("""
            UPDATE tasks
            SET status = 'running', updated_at = ?,
                result_data = COALESCE(?, result_data)
            WHERE id = ?
        """, (now_ms, result_json, task_id))

        if payload.workerId:
            execute_write(
                "UPDATE workers SET status = 'busy', current_task_id = ?, updated_at = ? WHERE id = ?",
                (task_id, now_ms, payload.workerId)
            )

    else:
        # Progress step update or transient heartbeat
        result_json = json.dumps(payload.result or {}, ensure_ascii=False) if payload.result else None
        execute_write("""
            UPDATE tasks
            SET updated_at = ?,
                result_data = COALESCE(?, result_data)
            WHERE id = ?
        """, (now_ms, result_json, task_id))

    add_activity_log(
        "TASK_STATUS_UPDATE",
        entity_type="task",
        entity_id=task_id,
        details={"status": raw_status or "progress", "workerId": payload.workerId, "error": payload.error}
    )

    return {"success": True, "status": "ok", "taskStatus": raw_status or "completed", "taskId": task_id}

@router.post("/{task_id}/heartbeat")
def extend_task_lease(task_id: str, payload: Dict[str, Any] = None):
    """Extends task lease lock expiration for long-running execution."""
    existing = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    task_status = existing.get("status")
    if task_status in ("cancelled", "completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot extend lease for task in '{task_status}' status"
        )

    payload = payload or {}
    extend_sec = int(payload.get("extendSec", 60))
    now_ms = int(time.time() * 1000)
    new_lease = now_ms + (extend_sec * 1000)

    execute_write("""
        UPDATE tasks
        SET lease_expires_at = ?, updated_at = ?
        WHERE id = ? AND status NOT IN ('cancelled', 'completed', 'failed')
    """, (new_lease, now_ms, task_id))

    return {"success": True, "taskId": task_id, "leaseExpiresAt": new_lease}

@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreateRequest):
    """Enqueues a new automation task."""
    now_ms = int(time.time() * 1000)
    rand_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    task_id = payload.id.strip() if (payload.id and payload.id.strip()) else f"task_{now_ms}_{rand_str}"
    scheduled_time = payload.scheduledTime or now_ms
    max_retries = payload.maxRetries if payload.maxRetries is not None else 3

    account_id = payload.accountId
    if account_id:
        acc = query_one("SELECT id FROM accounts WHERE id = ? OR target_id = ?", (account_id, account_id))
        if acc:
            account_id = acc["id"]

    worker_id = payload.workerId
    post_id = payload.postId

    execute_write("""
        INSERT INTO tasks (
            id, task_type, project_key, worker_id, account_id, post_id,
            priority, status, payload, scheduled_time, retry_count,
            max_retries, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, ?, ?, ?)
    """, (
        task_id,
        payload.taskType,
        payload.projectKey or "all",
        worker_id,
        account_id,
        post_id,
        payload.priority or 0,
        json.dumps(payload.payload or {}, ensure_ascii=False),
        scheduled_time,
        max_retries,
        now_ms,
        now_ms
    ))

    add_activity_log("CREATE_TASK", entity_type="task", entity_id=task_id, project_key=payload.projectKey or "all")
    created = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    return {"success": True, "status": "pending", "task": format_task(created)}

@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    """
    Cancels a pending, assigned, or running task.
    Releases assigned worker node from execution lock and resets lease expiration.
    """
    existing = query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    current_status = existing.get("status")
    if current_status == "completed":
        return {
            "success": False,
            "message": "Nhiệm vụ đã hoàn thành trước đó, không thể hủy",
            "taskId": task_id,
            "status": "completed"
        }

    now_ms = int(time.time() * 1000)

    execute_write("""
        UPDATE tasks
        SET status = 'cancelled', lease_expires_at = NULL, updated_at = ?
        WHERE id = ?
    """, (now_ms, task_id))

    # Free up worker if assigned to this task and restore online status if busy
    worker_id = existing.get("worker_id")
    if worker_id:
        execute_write(
            """
            UPDATE workers
            SET current_task_id = NULL,
                status = CASE WHEN status = 'busy' THEN 'online' ELSE status END
            WHERE id = ? AND current_task_id = ?
            """,
            (worker_id, task_id)
        )

    add_activity_log(
        "CANCEL_TASK",
        entity_type="task",
        entity_id=task_id,
        project_key=existing.get("project_key") or "all",
        details={
            "taskId": task_id,
            "previousStatus": current_status,
            "workerId": worker_id,
            "cancelledAt": now_ms,
            "source": "admin_ui"
        }
    )

    return {
        "success": True,
        "status": "cancelled",
        "taskId": task_id,
        "message": f"Nhiệm vụ {task_id} đã được hủy bỏ thành công"
    }
