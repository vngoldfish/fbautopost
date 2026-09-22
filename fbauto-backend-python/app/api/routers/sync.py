"""
app/api/routers/sync.py
APIRouter for Chrome Extension Sync protocol (100% backward-compatible with Extension v7.0).
Provides status, captcha/theme configuration, token capture, and auto-post result reporting.
"""

import time
import json
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Header
from app.core.security import serialize_theme, parse_theme
from app.db.session import query_one, execute_write, add_activity_log
from app.api.routers.posts import format_post

router = APIRouter(prefix="/sync", tags=["Sync (Extension Legacy)"])

@router.get("/status")
def sync_status(request: Request):
    """Extension heartbeat & connection status probe."""
    now_ms = int(time.time() * 1000)

    # If worker/extension sends X-Ext-Id or X-Worker-Id, record presence
    worker_id = request.headers.get("X-Ext-Id") or request.headers.get("X-Worker-Id")
    if worker_id:
        existing = query_one("SELECT id FROM workers WHERE id = ?", (worker_id,))
        if existing:
            execute_write(
                "UPDATE workers SET status = 'online', last_heartbeat = ?, updated_at = ? WHERE id = ?",
                (now_ms, now_ms, worker_id)
            )
        else:
            execute_write("""
                INSERT INTO workers (id, name, project_key, status, last_heartbeat, created_at, updated_at)
                VALUES (?, ?, 'all', 'online', ?, ?, ?)
            """, (worker_id, f"Node-{worker_id[-6:]}", now_ms, now_ms, now_ms))

    return {
        "status": "ok",
        "version": "7.0.0",
        "timestamp": now_ms,
        "service": "fbauto-backend-python"
    }

@router.get("/config")
def sync_config():
    """Returns mock configuration for Extension background scripts."""
    return {
        "recaptcha_ent_key": "6Ld_sample_key_for_testing",
        "recaptcha_action": "flow"
    }

@router.get("/theme")
def sync_theme():
    """Returns theme handshake XOR 0x5A encrypted data for Extension."""
    payload = {"r": None, "g": 0, "x": None}
    return {
        "d": serialize_theme(json.dumps(payload))
    }

@router.post("/render")
async def sync_render(request: Request):
    """Captures authentication token or diagnostic reports from Extension."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if "d" in payload:
        try:
            payload = json.loads(parse_theme(payload["d"]))
        except Exception:
            pass

    now_ms = int(time.time() * 1000)
    tok_id = f"tok_{now_ms}"
    execute_write("""
        INSERT INTO tokens (id, request_id, token, error, user_agent, received_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        tok_id,
        payload.get("r"),
        payload.get("t"),
        payload.get("e"),
        payload.get("u"),
        now_ms
    ))
    return {"success": True}

@router.post("/auto-post")
async def sync_auto_post(request: Request):
    """Extension reports task completion or execution result."""
    try:
        post_data = await request.json()
    except Exception:
        post_data = {}

    post_id = post_data.get("id")
    target_status = post_data.get("status") or "completed"
    now_ms = int(time.time() * 1000)

    updated = None
    if post_id:
        existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
        if existing:
            execute_write("""
                UPDATE posts
                SET status = ?, executed_at = ?, source = 'chrome_extension',
                    fb_post_id = COALESCE(?, fb_post_id),
                    fb_post_url = COALESCE(?, fb_post_url),
                    execution_method = COALESCE(?, execution_method),
                    last_error = ?, updated_at = ?
                WHERE id = ?
            """, (
                target_status,
                now_ms,
                post_data.get("fbPostId"),
                post_data.get("fbPostUrl"),
                post_data.get("executionMethod"),
                post_data.get("error"),
                now_ms,
                post_id
            ))
            updated = format_post(query_one("SELECT * FROM posts WHERE id = ?", (post_id,)))

    if not updated:
        # If post didn't exist before, register it
        new_id = post_id or f"post_{now_ms}"
        execute_write("""
            INSERT INTO posts (
                id, content, post_type, target_url, status, scheduled_time,
                executed_at, source, execution_method, fb_post_id, fb_post_url,
                last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'chrome_extension', ?, ?, ?, ?, ?, ?)
        """, (
            new_id,
            post_data.get("content") or "",
            post_data.get("postType") or "post",
            post_data.get("targetUrl") or "",
            target_status,
            now_ms,
            now_ms,
            post_data.get("executionMethod"),
            post_data.get("fbPostId"),
            post_data.get("fbPostUrl"),
            post_data.get("error"),
            now_ms,
            now_ms
        ))
        updated = format_post(query_one("SELECT * FROM posts WHERE id = ?", (new_id,)))

    add_activity_log("EXTENSION_AUTO_POST", entity_type="post", entity_id=updated["id"])
    return {
        "success": True,
        "message": "Post updated and logged by Python backend",
        "post": updated
    }

# Legacy Stubs for Extension Compatibility
@router.get("/grok-poll-task")
def sync_grok_poll_task():
    return {"task": None}

@router.post("/grok-event")
@router.post("/google-one-activity")
@router.post("/google-flow-page")
def sync_legacy_stubs():
    return {"success": True}
