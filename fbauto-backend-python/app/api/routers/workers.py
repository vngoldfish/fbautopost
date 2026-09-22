"""
app/api/routers/workers.py
APIRouter for Chrome Extension Worker Node registry, heartbeat, status monitoring, and account assignment.
Provides distributed worker orchestration for Milestone 2.
"""

import time
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Query, status
from app.db.session import query_all, query_one, execute_write, transaction, add_activity_log
from app.models.worker import (
    WorkerRegisterRequest,
    WorkerHeartbeatRequest,
    WorkerAccountAssignRequest
)

router = APIRouter(prefix="/api/workers", tags=["Workers"])

def format_worker(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    assigned = []
    if row.get("assigned_accounts"):
        try:
            assigned = json.loads(row["assigned_accounts"])
        except Exception:
            pass

    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "projectKey": row.get("project_key") or "all",
        "status": row.get("status") or "offline",
        "ip": row.get("ip_address") or "",
        "version": row.get("extension_version") or "",
        "lastSeen": row.get("last_heartbeat"),
        "currentTaskId": row.get("current_task_id"),
        "assignedAccounts": assigned,
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at")
    }

@router.get("")
def list_workers(projectKey: Optional[str] = None):
    """Lists all registered worker nodes, optionally filtered by projectKey."""
    sql = "SELECT * FROM workers"
    params = []
    if projectKey and projectKey != "all":
        sql += " WHERE project_key = ?"
        params.append(projectKey)
    sql += " ORDER BY last_heartbeat DESC"

    rows = query_all(sql, tuple(params))
    now_ms = int(time.time() * 1000)

    # Calculate online/offline status (offline if no heartbeat for 45s)
    workers = []
    for r in rows:
        w = format_worker(r)
        if now_ms - (w["lastSeen"] or 0) > 45000 and w["status"] != "busy":
            w["status"] = "offline"
        workers.append(w)

    return {"workers": workers, "total": len(workers)}

@router.post("/register")
async def register_worker(request: Request, payload: WorkerRegisterRequest):
    """Registers or updates a Chrome Extension Worker Node."""
    worker_id = payload.workerId.strip()
    if not worker_id:
        raise HTTPException(status_code=400, detail="Missing workerId")

    name = (payload.name or f"Node-{worker_id[-6:]}").strip()
    project_key = (payload.projectKey or "all").strip()
    version = payload.version or "7.0.0"
    assigned_accs_list = payload.assignedAccounts or []
    assigned_accs = json.dumps(assigned_accs_list, ensure_ascii=False)

    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    now_ms = int(time.time() * 1000)

    execute_write("""
        INSERT INTO workers (
            id, name, project_key, status, ip_address, extension_version,
            last_heartbeat, assigned_accounts, created_at, updated_at
        ) VALUES (?, ?, ?, 'online', ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            project_key = excluded.project_key,
            status = 'online',
            ip_address = excluded.ip_address,
            extension_version = excluded.extension_version,
            last_heartbeat = excluded.last_heartbeat,
            assigned_accounts = excluded.assigned_accounts,
            updated_at = excluded.updated_at
    """, (
        worker_id, name, project_key, client_ip, version,
        now_ms, assigned_accs, now_ms, now_ms
    ))

    # Link assigned accounts in accounts table if any
    for acc in assigned_accs_list:
        execute_write("""
            UPDATE accounts
            SET worker_id = ?, updated_at = ?
            WHERE id = ? OR target_id = ?
        """, (worker_id, now_ms, acc, acc))

    add_activity_log("WORKER_REGISTERED", entity_type="worker", entity_id=worker_id, project_key=project_key)

    return {
        "success": True,
        "status": "ok",
        "workerId": worker_id,
        "worker": {
            "id": worker_id,
            "name": name,
            "projectKey": project_key,
            "status": "online"
        },
        "config": {
            "pollIntervalMs": 5000,
            "heartbeatIntervalMs": 15000,
            "projectKey": project_key
        }
    }

@router.post("/heartbeat")
async def worker_heartbeat(request: Request, payload: WorkerHeartbeatRequest):
    """Receives periodic liveness heartbeat from Worker Node."""
    worker_id = payload.workerId.strip()
    now_ms = int(time.time() * 1000)

    # Check for pending tasks in queue
    pending_count_row = query_one("""
        SELECT count(*) as cnt FROM tasks
        WHERE status = 'pending' AND scheduled_time <= ?
        AND (worker_id = ? OR worker_id IS NULL)
    """, (now_ms, worker_id))
    has_pending = bool(pending_count_row and pending_count_row["cnt"] > 0)

    status_val = payload.status or "idle"
    if status_val not in ["idle", "busy", "paused", "error", "online"]:
        status_val = "idle"

    execute_write("""
        UPDATE workers
        SET status = ?, current_task_id = ?, last_heartbeat = ?, updated_at = ?
        WHERE id = ?
    """, (status_val, payload.currentTaskId, now_ms, now_ms, worker_id))

    return {
        "success": True,
        "status": status_val if status_val in ["busy", "ok"] else "ok",
        "timestamp": now_ms,
        "hasPendingTasks": has_pending
    }

@router.put("/{worker_id}/accounts")
def set_worker_accounts(worker_id: str, payload: WorkerAccountAssignRequest):
    """
    Sets or replaces the accounts assigned to a worker node.
    Updates assigned_accounts in workers table and sets worker_id in accounts table.
    """
    existing = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Worker not found")

    raw_ids = payload.accountIds or []
    final_accounts = list(dict.fromkeys([x.strip() for x in raw_ids if x and x.strip()]))
    now_ms = int(time.time() * 1000)

    with transaction() as conn:
        # Update worker record
        conn.execute("""
            UPDATE workers
            SET assigned_accounts = ?, updated_at = ?
            WHERE id = ?
        """, (json.dumps(final_accounts, ensure_ascii=False), now_ms, worker_id))

        # Clear previously assigned accounts for this worker
        conn.execute("""
            UPDATE accounts
            SET worker_id = NULL, updated_at = ?
            WHERE worker_id = ?
        """, (now_ms, worker_id))

        # Set worker_id on newly assigned accounts
        for acc in final_accounts:
            conn.execute("""
                UPDATE accounts
                SET worker_id = ?, updated_at = ?
                WHERE id = ? OR target_id = ?
            """, (worker_id, now_ms, acc, acc))

    add_activity_log(
        "WORKER_ACCOUNTS_ASSIGNED",
        entity_type="worker",
        entity_id=worker_id,
        details={"workerId": worker_id, "accountIds": final_accounts, "action": "set"}
    )

    updated = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    return {
        "success": True,
        "workerId": worker_id,
        "assignedAccounts": final_accounts,
        "worker": format_worker(updated)
    }

@router.post("/{worker_id}/assign")
def assign_worker_accounts(worker_id: str, payload: WorkerAccountAssignRequest):
    """
    Appends or assigns accounts to a worker node.
    Updates assigned_accounts in workers table and sets worker_id in accounts table.
    """
    existing = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Worker not found")

    curr_assigned = []
    if existing.get("assigned_accounts"):
        try:
            curr_assigned = json.loads(existing["assigned_accounts"])
        except Exception:
            pass

    incoming = [x.strip() for x in (payload.accountIds or []) if x and x.strip()]
    merged_accounts = list(dict.fromkeys(curr_assigned + incoming))
    now_ms = int(time.time() * 1000)

    with transaction() as conn:
        conn.execute("""
            UPDATE workers
            SET assigned_accounts = ?, updated_at = ?
            WHERE id = ?
        """, (json.dumps(merged_accounts, ensure_ascii=False), now_ms, worker_id))

        for acc in incoming:
            conn.execute("""
                UPDATE accounts
                SET worker_id = ?, updated_at = ?
                WHERE id = ? OR target_id = ?
            """, (worker_id, now_ms, acc, acc))

    add_activity_log(
        "WORKER_ACCOUNTS_ASSIGNED",
        entity_type="worker",
        entity_id=worker_id,
        details={"workerId": worker_id, "assignedAccounts": merged_accounts, "added": incoming, "action": "append"}
    )

    updated = query_one("SELECT * FROM workers WHERE id = ?", (worker_id,))
    return {
        "success": True,
        "workerId": worker_id,
        "assignedAccounts": merged_accounts,
        "worker": format_worker(updated)
    }

@router.delete("/{worker_id}")
def delete_worker(worker_id: str):
    """Removes a worker node registration and unassigns linked accounts."""
    existing = query_one("SELECT id FROM workers WHERE id = ?", (worker_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Worker not found")

    with transaction() as conn:
        conn.execute("UPDATE accounts SET worker_id = NULL WHERE worker_id = ?", (worker_id,))
        conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))

    add_activity_log("DELETE_WORKER", entity_type="worker", entity_id=worker_id)
    return {"success": True, "id": worker_id}
