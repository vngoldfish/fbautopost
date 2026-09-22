"""
fbauto-backend-python/database.py
Legacy database adapter providing drop-in compatibility for get_collection, insert_item,
update_item, delete_item, and add_log backed by the SQLite WAL engine.
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.db.session import query_all, query_one, execute_write, add_activity_log, transaction
from app.api.routers.posts import format_post
from app.api.routers.accounts import format_account
from app.api.routers.projects import format_project

def get_collection(name: str) -> list:
    """Retrieves collection records from SQLite WAL database."""
    if name == "posts":
        rows = query_all("SELECT * FROM posts ORDER BY scheduled_time ASC")
        return [format_post(r) for r in rows]

    elif name == "accounts":
        rows = query_all("SELECT * FROM accounts ORDER BY created_at DESC")
        return [format_account(r) for r in rows]

    elif name == "projects":
        rows = query_all("SELECT * FROM projects ORDER BY created_at ASC")
        return [format_project(r) for r in rows]

    elif name == "settings":
        row = query_one("SELECT value FROM settings WHERE key = 'cfg_main'")
        if row and row.get("value"):
            try:
                return [json.loads(row["value"])]
            except Exception:
                pass
        return []

    elif name == "logs":
        rows = query_all("SELECT * FROM logs ORDER BY created_at DESC LIMIT 500")
        logs = []
        for r in rows:
            details = {}
            if r.get("details"):
                try:
                    details = json.loads(r["details"]) if isinstance(r["details"], str) else r["details"]
                except Exception:
                    pass
            logs.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "action": r["action"],
                "details": details
            })
        return logs

    elif name == "targets":
        rows = query_all("SELECT * FROM targets ORDER BY updated_at DESC")
        targets = []
        for r in rows:
            try:
                targets.append(json.loads(r.get("raw_data") or "{}"))
            except Exception:
                targets.append({"id": r["id"], "name": r["name"], "type": r["target_type"]})
        return targets

    elif name == "tokens":
        rows = query_all("SELECT * FROM tokens ORDER BY received_at DESC")
        return [dict(r) for r in rows]

    return []

def save_collection(name: str, data: list):
    """Legacy bulk save helper adapted for SQLite."""
    now_ms = int(time.time() * 1000)
    if name == "settings" and data:
        cfg = data[0] if isinstance(data, list) else data
        execute_write(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('cfg_main', ?, ?)",
            (json.dumps(cfg, ensure_ascii=False), now_ms)
        )
    elif name == "targets" and isinstance(data, list):
        for t in data:
            if isinstance(t, dict) and t.get("id"):
                execute_write(
                    "INSERT OR REPLACE INTO targets (id, name, target_type, raw_data, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (str(t["id"]), str(t.get("name") or t["id"]), str(t.get("type") or "page"), json.dumps(t, ensure_ascii=False), now_ms)
                )

def insert_item(name: str, item: dict) -> dict:
    """Inserts a single item into the appropriate table."""
    now_ms = int(time.time() * 1000)
    if name == "posts":
        from app.api.routers.posts import create_post
        from app.models.post import PostCreateRequest
        # Insert directly
        post_id = item.get("id") or f"post_{now_ms}"
        execute_write("""
            INSERT OR REPLACE INTO posts (
                id, project_key, post_type, content, target_type, target_url,
                target_id, actor_id, access_token, media_url, media_path,
                scheduled_time, repeat_interval_minutes, source, status,
                retry_count, max_retries, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            item.get("projectKey") or "all",
            item.get("postType") or "post",
            item.get("content") or "",
            item.get("targetType") or "profile",
            item.get("targetUrl") or "",
            item.get("targetId") or "",
            item.get("actorId") or "",
            item.get("accessToken") or "",
            item.get("mediaUrl") or "",
            item.get("mediaPath"),
            item.get("scheduledTime") or now_ms,
            item.get("repeatIntervalMinutes") or 0,
            item.get("source") or "api",
            item.get("status") or "pending",
            item.get("retryCount") or 0,
            item.get("maxRetries") or 3,
            item.get("createdAt") or now_ms,
            now_ms
        ))
        item["id"] = post_id
        return item

    elif name == "accounts":
        acc_id = item.get("id") or f"acc_{now_ms}"
        target_id = item.get("targetId") or f"uid_{now_ms}"
        execute_write("""
            INSERT OR REPLACE INTO accounts (
                id, target_id, name, account_type, project_key, worker_id,
                access_token, status, cookie_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'valid', ?, ?)
        """, (
            acc_id,
            target_id,
            item.get("name") or target_id,
            item.get("type") or "profile",
            item.get("projectKey") or "all",
            item.get("workerId"),
            item.get("accessToken") or "",
            item.get("status") or "active",
            item.get("createdAt") or now_ms,
            now_ms
        ))
        item["id"] = acc_id
        return item

    elif name == "projects":
        p_id = item.get("id") or f"proj_{now_ms}"
        execute_write("""
            INSERT OR REPLACE INTO projects (id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (p_id, item.get("name") or p_id, item.get("description") or "", item.get("createdAt") or now_ms, now_ms))
        item["id"] = p_id
        return item

    elif name == "tokens":
        tok_id = item.get("id") or f"tok_{now_ms}"
        execute_write("""
            INSERT INTO tokens (id, request_id, token, error, user_agent, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tok_id,
            item.get("requestId"),
            item.get("token"),
            item.get("error"),
            item.get("userAgent"),
            item.get("receivedAt") or now_ms
        ))
        item["id"] = tok_id
        return item

    return item

def update_item(name: str, item_id: str, updates: dict) -> Optional[dict]:
    """Updates fields on an item in the appropriate table."""
    now_ms = int(time.time() * 1000)
    if name == "posts":
        from app.api.routers.posts import format_post
        row = query_one("SELECT * FROM posts WHERE id = ?", (item_id,))
        if not row:
            return None

        fields = []
        values = []
        col_map = {
            "status": "status",
            "progressStep": "progress_step",
            "lastError": "last_error",
            "onlyAction": "only_action",
            "executedAt": "executed_at",
            "fbPostId": "fb_post_id",
            "fbPostUrl": "fb_post_url",
            "retryCount": "retry_count",
            "scheduledTime": "scheduled_time",
            "targetCommentId": "target_comment_id",
            "lastReplyStatus": "last_reply_status"
        }
        for k, col in col_map.items():
            if k in updates:
                fields.append(f"{col} = ?")
                values.append(updates[k])

        if "comments" in updates:
            fields.append("comments = ?")
            values.append(json.dumps(updates["comments"], ensure_ascii=False))

        if "seedingComments" in updates:
            fields.append("seeding_comments = ?")
            values.append(json.dumps(updates["seedingComments"], ensure_ascii=False))

        if "autoReplyComments" in updates:
            fields.append("auto_reply_comments = ?")
            values.append(json.dumps(updates["autoReplyComments"], ensure_ascii=False))

        if fields:
            fields.append("updated_at = ?")
            values.append(now_ms)
            values.append(item_id)
            execute_write(f"UPDATE posts SET {', '.join(fields)} WHERE id = ?", tuple(values))

        updated_row = query_one("SELECT * FROM posts WHERE id = ?", (item_id,))
        return format_post(updated_row)

    return None

def delete_item(name: str, item_id: str) -> bool:
    """Deletes an item from the appropriate table."""
    if name == "posts":
        rc = execute_write("DELETE FROM posts WHERE id = ?", (item_id,))
        return rc > 0
    elif name == "accounts":
        rc = execute_write("DELETE FROM accounts WHERE id = ? OR target_id = ?", (item_id, item_id))
        return rc > 0
    elif name == "projects":
        rc = execute_write("DELETE FROM projects WHERE id = ?", (item_id,))
        return rc > 0
    return False

def add_log(action: str, details: dict = None) -> dict:
    """Logs an activity event."""
    log_id = add_activity_log(
        action=action,
        entity_type=(details or {}).get("entityType", ""),
        entity_id=(details or {}).get("postId") or (details or {}).get("accId") or "",
        details=details
    )
    return {
        "id": log_id,
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    }
