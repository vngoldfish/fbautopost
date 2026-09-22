"""
app/api/routers/accounts.py
APIRouter for Facebook Accounts, Health Status Management, and Discovered Targets.
Enforces deduplication by targetId / fb_id and provides quarantine on checkpoint/expired status.
"""

import time
import json
import uuid
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status
from app.db.session import query_all, query_one, execute_write, add_activity_log
from app.models.account import (
    AccountCreateRequest,
    TargetSyncRequest,
    AccountHealthRequest,
    AccountUpdateRequest
)

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])

def _ensure_health_status_column():
    """Ensures health_status column exists in the accounts table."""
    try:
        execute_write("ALTER TABLE accounts ADD COLUMN health_status TEXT DEFAULT 'live'")
    except Exception:
        pass

# Ensure column exists at startup
_ensure_health_status_column()

def format_account(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Maps database row to camelCase account format."""
    if not row:
        return None
    raw_status = row.get("status") or "active"
    h_status = row.get("health_status") or ("live" if raw_status == "active" else raw_status)
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("account_type") or "profile",
        "targetId": row.get("target_id") or "",
        "projectKey": row.get("project_key") or "all",
        "workerId": row.get("worker_id"),
        "accessToken": row.get("access_token") or "",
        "status": raw_status,
        "healthStatus": h_status,
        "cookieStatus": row.get("cookie_status") or "valid",
        "dailyPostCount": row.get("daily_post_count") or 0,
        "dailyActionCount": row.get("daily_action_count") or 0,
        "lastActionAt": row.get("last_action_at"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at")
    }

def _apply_health_update(
    account_id: str,
    raw_status: str,
    checkpoint_type: Optional[str] = None,
    message: Optional[str] = None,
    detected_at: Optional[int] = None
) -> Dict[str, Any]:
    _ensure_health_status_column()
    now_ms = int(time.time() * 1000)
    norm = raw_status.strip().lower()

    if norm in ["live", "healthy", "active", "ok"]:
        db_status = "active"
        health_status = "live"
        cookie_status = "valid"
    elif norm in ["checkpoint", "locked"]:
        db_status = "checkpoint"
        health_status = "locked" if norm == "locked" else "checkpoint"
        cookie_status = "invalid"
    elif norm in ["expired"]:
        db_status = "expired"
        health_status = "expired"
        cookie_status = "expired"
    elif norm in ["logged_out", "unauthorized"]:
        db_status = "logged_out"
        health_status = "expired"
        cookie_status = "invalid"
    else:
        db_status = "checkpoint"
        health_status = norm
        cookie_status = "invalid"

    existing = query_one("SELECT * FROM accounts WHERE id = ? OR target_id = ?", (account_id, account_id))
    if existing:
        real_id = existing["id"]
        execute_write("""
            UPDATE accounts
            SET status = ?, health_status = ?, cookie_status = ?, updated_at = ?
            WHERE id = ?
        """, (db_status, health_status, cookie_status, now_ms, real_id))
    else:
        real_id = account_id
        execute_write("""
            INSERT INTO accounts (
                id, target_id, name, account_type, project_key,
                access_token, status, health_status, cookie_status, daily_post_count,
                daily_action_count, created_at, updated_at
            ) VALUES (?, ?, ?, 'profile', 'all', '', ?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET
                status = excluded.status,
                health_status = excluded.health_status,
                cookie_status = excluded.cookie_status,
                updated_at = excluded.updated_at
        """, (
            real_id, account_id, f"Account {account_id}",
            db_status, health_status, cookie_status, now_ms, now_ms
        ))

    # If status is checkpoint or expired (or locked), abort/quarantine running tasks assigned to this account
    if db_status in ["checkpoint", "expired", "logged_out"]:
        execute_write("""
            UPDATE tasks
            SET status = 'cancelled',
                lease_expires_at = NULL,
                last_error = ?,
                updated_at = ?
            WHERE (account_id = ? OR account_id = ?)
              AND status IN ('pending', 'assigned', 'running')
        """, (f"Account {db_status}: tasks quarantined", now_ms, account_id, real_id))

        add_activity_log(
            "ACCOUNT_CHECKPOINT" if db_status == "checkpoint" else "ACCOUNT_EXPIRED",
            entity_type="account",
            entity_id=real_id,
            details={
                "healthStatus": health_status,
                "status": db_status,
                "checkpointType": checkpoint_type,
                "message": message,
                "detectedAt": detected_at or now_ms
            }
        )
    else:
        add_activity_log(
            "ACCOUNT_RECOVERY",
            entity_type="account",
            entity_id=real_id,
            details={
                "healthStatus": health_status,
                "status": db_status,
                "detectedAt": detected_at or now_ms
            }
        )

    saved_row = query_one("SELECT * FROM accounts WHERE id = ?", (real_id,))
    return {
        "success": True,
        "status": db_status,
        "healthStatus": health_status,
        "accountId": real_id,
        "account": format_account(saved_row)
    }

@router.get("")
def list_accounts():
    """Retrieves all deduplicated Facebook accounts."""
    _ensure_health_status_column()
    rows = query_all("SELECT * FROM accounts ORDER BY created_at DESC")
    accounts = [format_account(r) for r in rows]
    return {"accounts": accounts, "total": len(accounts)}

@router.post("", status_code=status.HTTP_201_CREATED)
def create_or_upsert_account(payload: AccountCreateRequest):
    """Adds or updates a Facebook account with deduplication on targetId via atomic SQLite upsert."""
    _ensure_health_status_column()
    name = payload.name.strip()
    access_token = payload.accessToken.strip()

    if not name or not access_token:
        raise HTTPException(status_code=400, detail="Name and Access Token are required")

    target_id = (payload.targetId or "").strip()
    now_ms = int(time.time() * 1000)
    if not target_id:
        target_id = f"uid_{now_ms}_{uuid.uuid4().hex[:6]}"

    acc_id = payload.id.strip() if (payload.id and payload.id.strip()) else f"acc_{now_ms}_{uuid.uuid4().hex[:6]}"
    acc_type = payload.type or "page"
    if acc_type not in ["profile", "page", "group", "user"]:
        acc_type = "profile"

    # Atomic Upsert: Preserves id and created_at on conflict, updates dynamic fields
    execute_write("""
        INSERT INTO accounts (
            id, target_id, name, account_type, project_key, worker_id,
            access_token, status, health_status, cookie_status, daily_post_count,
            daily_action_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'live', 'valid', 0, 0, ?, ?)
        ON CONFLICT(target_id) DO UPDATE SET
            name = excluded.name,
            account_type = excluded.account_type,
            project_key = CASE 
                WHEN excluded.project_key IS NOT NULL AND excluded.project_key != '' AND excluded.project_key != 'all' 
                THEN excluded.project_key 
                ELSE accounts.project_key 
            END,
            worker_id = COALESCE(excluded.worker_id, accounts.worker_id),
            access_token = excluded.access_token,
            status = 'active',
            health_status = 'live',
            updated_at = excluded.updated_at
    """, (
        acc_id,
        target_id,
        name,
        acc_type,
        payload.projectKey or "all",
        payload.workerId,
        access_token,
        now_ms,
        now_ms
    ))

    # Fetch committed record (guarantees reading the single source of truth)
    saved_row = query_one("SELECT * FROM accounts WHERE target_id = ?", (target_id,))
    real_id = saved_row["id"] if saved_row else acc_id

    add_activity_log(
        "ADD_FB_ACCOUNT",
        entity_type="account",
        entity_id=real_id,
        details={"accId": real_id, "name": name, "targetId": target_id}
    )

    return {"success": True, "account": format_account(saved_row)}

@router.post("/{account_id}/health")
def update_account_health(account_id: str, payload: AccountHealthRequest):
    """
    Updates Facebook account health status (live | checkpoint | expired | locked).
    Quarantines account by invalidating cookies and aborting active tasks if checkpoint/expired.
    """
    raw_status = payload.healthStatus or payload.status or "checkpoint"
    checkpoint_type = payload.checkpointType
    message = payload.checkpointMessage or payload.message
    detected_at = payload.detectedAt
    return _apply_health_update(account_id, raw_status, checkpoint_type, message, detected_at)

@router.patch("/{account_id}")
def patch_account(account_id: str, payload: AccountUpdateRequest):
    """
    Patches Facebook account properties (healthStatus, name, workerId, accessToken, etc.).
    """
    _ensure_health_status_column()
    existing = query_one("SELECT * FROM accounts WHERE id = ? OR target_id = ?", (account_id, account_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    real_id = existing["id"]
    now_ms = int(time.time() * 1000)

    # If health status is explicitly provided, update health and quarantine if needed
    if payload.healthStatus or payload.status:
        raw_status = payload.healthStatus or payload.status
        checkpoint_type = payload.checkpointType
        message = payload.checkpointMessage or payload.message
        _apply_health_update(real_id, raw_status, checkpoint_type, message)

    # Update any other scalar fields if provided
    updates = []
    params = []
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name.strip())
    if payload.workerId is not None:
        updates.append("worker_id = ?")
        params.append(payload.workerId.strip() if payload.workerId else None)
    if payload.projectKey is not None:
        updates.append("project_key = ?")
        params.append(payload.projectKey.strip())
    if payload.accessToken is not None:
        updates.append("access_token = ?")
        params.append(payload.accessToken.strip())
    if payload.cookieStatus is not None:
        updates.append("cookie_status = ?")
        params.append(payload.cookieStatus.strip())

    if updates:
        updates.append("updated_at = ?")
        params.append(now_ms)
        params.append(real_id)
        execute_write(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
        add_activity_log("ACCOUNT_UPDATED", entity_type="account", entity_id=real_id)

    updated = query_one("SELECT * FROM accounts WHERE id = ?", (real_id,))
    formatted = format_account(updated)
    return {
        "success": True,
        "status": formatted.get("status"),
        "healthStatus": formatted.get("healthStatus"),
        "accountId": real_id,
        "account": formatted
    }

@router.get("/targets")
def list_targets():
    """Retrieves all discovered Fanpages and Groups."""
    rows = query_all("SELECT * FROM targets ORDER BY updated_at DESC")
    targets = []
    for r in rows:
        raw_str = r.get("raw_data") or "{}"
        try:
            target_obj = json.loads(raw_str)
        except Exception:
            target_obj = {"id": r["id"], "name": r["name"], "type": r["target_type"]}
        targets.append(target_obj)
    return {"targets": targets, "total": len(targets)}

@router.post("/targets")
def sync_targets(payload: TargetSyncRequest):
    """Syncs discovered Fanpages and Groups from the Extension."""
    now_ms = int(time.time() * 1000)
    count = 0
    for t in payload.targets:
        if isinstance(t, dict) and t.get("id"):
            target_id = str(t["id"])
            name = str(t.get("name") or target_id)
            target_type = str(t.get("type") or "page")
            execute_write("""
                INSERT OR REPLACE INTO targets (id, name, target_type, raw_data, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (target_id, name, target_type, json.dumps(t, ensure_ascii=False), now_ms))
            count += 1

    add_activity_log("SYNC_TARGETS", entity_type="target", details={"count": count})
    return {"success": True, "count": count}

@router.delete("/{account_id}")
def delete_account(account_id: str):
    """Deletes an account by ID or targetId."""
    existing = query_one("SELECT id FROM accounts WHERE id = ? OR target_id = ?", (account_id, account_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    real_id = existing["id"]
    execute_write("DELETE FROM accounts WHERE id = ?", (real_id,))
    add_activity_log("DELETE_FB_ACCOUNT", entity_type="account", entity_id=real_id, details={"accId": real_id})
    return {"success": True, "id": real_id}
