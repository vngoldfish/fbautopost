"""
app/api/routers/posts.py
APIRouter for Facebook Post management:
CRUD, immediate execution, comments sync, live fetch, reply, reaction, and media offloading.
"""

import time
import json
import random
import string
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse

from app.db.session import query_all, query_one, execute_write, add_activity_log, transaction
from app.services.media_service import save_base64_media
from app.models.post import (
    PostCreateRequest, PostUpdateRequest, RunNowRequest,
    SyncCommentRequest, ReplyCommentRequest, ReactCommentRequest
)

router = APIRouter(prefix="/api/posts", tags=["Posts"])

def format_post(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Converts a SQLite row dictionary into standard camelCase JSON representation."""
    if not row:
        return None

    def _parse_json(val, default):
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str) and val.strip():
            try:
                return json.loads(val)
            except Exception:
                pass
        return default

    return {
        "id": row.get("id"),
        "projectKey": row.get("project_key") or "all",
        "postType": row.get("post_type") or "post",
        "content": row.get("content") or "",
        "targetType": row.get("target_type") or "profile",
        "targetUrl": row.get("target_url") or "",
        "targetId": row.get("target_id") or "",
        "actorId": row.get("actor_id") or "",
        "accessToken": row.get("access_token") or "",
        "mediaUrl": row.get("media_url") or "",
        "mediaPath": row.get("media_path") or "",
        "seedingComments": _parse_json(row.get("seeding_comments"), []),
        "autoReplyComments": _parse_json(row.get("auto_reply_comments"), []),
        "autoReactType": row.get("auto_react_type") or "NONE",
        "metrics": _parse_json(row.get("metrics"), {"likes": 0, "comments": 0, "shares": 0}),
        "scheduledTime": row.get("scheduled_time"),
        "repeatIntervalMinutes": row.get("repeat_interval_minutes") or 0,
        "source": row.get("source") or "api",
        "status": row.get("status") or "pending",
        "retryCount": row.get("retry_count") or 0,
        "maxRetries": row.get("max_retries") or 3,
        "lastError": row.get("last_error"),
        "progressStep": row.get("progress_step"),
        "executedAt": row.get("executed_at"),
        "executionMethod": row.get("execution_method"),
        "fbPostId": row.get("fb_post_id"),
        "fbPostUrl": row.get("fb_post_url"),
        "comments": _parse_json(row.get("comments"), []),
        "onlyAction": row.get("only_action"),
        "targetCommentId": row.get("target_comment_id"),
        "lastReplyStatus": row.get("last_reply_status"),
        "createdAt": row.get("created_at")
    }

@router.get("")
def list_posts(
    status: Optional[str] = None,
    postType: Optional[str] = None,
    type: Optional[str] = None,
    projectKey: Optional[str] = None,
    project: Optional[str] = None
):
    """Retrieves all posts with optional filtering by status, postType, or projectKey."""
    effective_post_type = postType or type
    effective_project = projectKey or project

    sql = "SELECT * FROM posts WHERE 1=1"
    params = []

    if status and status != "all":
        sql += " AND status = ?"
        params.append(status)

    if effective_post_type and effective_post_type != "all":
        sql += " AND post_type = ?"
        params.append(effective_post_type)

    if effective_project and effective_project != "all":
        sql += " AND (project_key = ? OR project_key = 'all' OR project_key IS NULL)"
        params.append(effective_project)

    sql += " ORDER BY scheduled_time ASC"

    rows = query_all(sql, tuple(params))
    posts = [format_post(r) for r in rows]
    return {"posts": posts, "total": len(posts)}

@router.get("/{post_id}")
def get_post(post_id: str):
    """Retrieves a single post by ID."""
    row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "post": format_post(row)}

@router.post("", status_code=status.HTTP_201_CREATED)
def create_post(payload: PostCreateRequest):
    """Creates a new Facebook post. Base64 media is automatically offloaded to physical disk storage."""
    content = payload.content or ""
    media_url = payload.mediaUrl or ""
    media_data = payload.mediaData

    if not content and not media_url and not media_data:
        raise HTTPException(
            status_code=400,
            detail="Nội dung, URL Media hoặc File đính kèm không được để trống"
        )

    post_type = payload.postType or payload.type or "post"
    if post_type not in ["post", "video", "reel", "story"]:
        post_type = "post"

    now_ms = int(time.time() * 1000)
    post_time = now_ms
    if payload.scheduledTime is not None:
        try:
            post_time = int(payload.scheduledTime)
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(str(payload.scheduledTime))
                post_time = int(dt.timestamp() * 1000)
            except Exception:
                post_time = now_ms

    rand_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    post_id = f"post_{now_ms}_{rand_str}"

    # Media offloading pipeline
    media_path = None
    if media_data:
        offloaded_url, offloaded_path = save_base64_media(media_data, post_id)
        if offloaded_url:
            media_url = offloaded_url
            media_path = offloaded_path
        else:
            # If mediaData is provided but fails decoding/validation, and post content is empty, reject with HTTP 400
            if not content.strip() and not media_url.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Invalid media payload and empty content"
                )

    try:
        repeat_interval = int(payload.repeatIntervalMinutes or 0)
    except (ValueError, TypeError):
        repeat_interval = 0

    project_key = payload.projectKey or payload.project or "all"
    target_type = payload.targetType or "profile"

    execute_write("""
        INSERT INTO posts (
            id, project_key, post_type, content, target_type, target_url,
            target_id, actor_id, access_token, media_url, media_path,
            seeding_comments, auto_reply_comments, auto_react_type,
            metrics, scheduled_time, repeat_interval_minutes, source,
            status, retry_count, max_retries, last_error, progress_step,
            comments, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post_id,
        project_key,
        post_type,
        content,
        target_type,
        payload.targetUrl or "",
        payload.targetId or "",
        payload.actorId or "",
        payload.accessToken or "",
        media_url,
        media_path,
        json.dumps(payload.seedingComments or [], ensure_ascii=False),
        json.dumps(payload.autoReplyComments or [], ensure_ascii=False),
        payload.autoReactType or "NONE",
        json.dumps(payload.metrics or {"likes": 0, "comments": 0, "shares": 0}, ensure_ascii=False),
        post_time,
        repeat_interval,
        payload.source or "api",
        "pending",
        0,
        3,
        None,
        "",
        json.dumps([], ensure_ascii=False),
        now_ms,
        now_ms
    ))

    add_activity_log(
        action="CREATE_POST",
        entity_type="post",
        entity_id=post_id,
        project_key=project_key,
        details={"postId": post_id, "postType": post_type, "scheduledTime": post_time}
    )

    created_row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return {"success": True, "post": format_post(created_row)}

@router.delete("/{post_id}")
def delete_post(post_id: str):
    """Deletes a post."""
    existing = query_one("SELECT id FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    execute_write("DELETE FROM posts WHERE id = ?", (post_id,))
    add_activity_log("DELETE_POST", entity_type="post", entity_id=post_id, details={"postId": post_id})
    return {"success": True, "id": post_id}

@router.post("/{post_id}/run-now")
def run_post_now(post_id: str, request_data: Optional[RunNowRequest] = None):
    """Forces immediate execution of a post."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    action = request_data.action if request_data else None
    now_ms = int(time.time() * 1000)
    scheduled_time = now_ms - 2000
    progress_step = f"🚀 Đang phát lệnh [{action or 'POST'}] cho Extension xử lý..."

    execute_write("""
        UPDATE posts
        SET status = 'pending', scheduled_time = ?, progress_step = ?,
            only_action = ?, last_error = NULL, updated_at = ?
        WHERE id = ?
    """, (scheduled_time, progress_step, action, now_ms, post_id))

    add_activity_log("TRIGGER_POST_NOW", entity_type="post", entity_id=post_id, details={"postId": post_id, "action": action})

    updated_row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return {"success": True, "post": format_post(updated_row)}

@router.patch("/{post_id}")
@router.put("/{post_id}")
async def update_post(post_id: str, request: Request):
    """Updates an existing post."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    try:
        body = await request.json()
    except Exception:
        body = {}

    now_ms = int(time.time() * 1000)
    fields = []
    values = []

    # Map fields to database columns
    field_map = {
        "content": "content",
        "postType": "post_type",
        "type": "post_type",
        "targetType": "target_type",
        "targetUrl": "target_url",
        "targetId": "target_id",
        "actorId": "actor_id",
        "accessToken": "access_token",
        "status": "status",
        "progressStep": "progress_step",
        "executionMethod": "execution_method",
        "fbPostId": "fb_post_id",
        "fbPostUrl": "fb_post_url",
        "lastError": "last_error",
        "onlyAction": "only_action",
        "targetCommentId": "target_comment_id",
        "lastReplyStatus": "last_reply_status",
        "autoReactType": "auto_react_type",
    }

    for json_key, col_name in field_map.items():
        if json_key in body:
            fields.append(f"{col_name} = ?")
            values.append(body[json_key])

    if "scheduledTime" in body:
        st = body["scheduledTime"]
        try:
            st = int(st)
        except Exception:
            pass
        fields.append("scheduled_time = ?")
        values.append(st)

    if "repeatIntervalMinutes" in body:
        try:
            rim = int(body["repeatIntervalMinutes"] or 0)
        except Exception:
            rim = 0
        fields.append("repeat_interval_minutes = ?")
        values.append(rim)

    if "mediaUrl" in body:
        fields.append("media_url = ?")
        values.append(body["mediaUrl"])

    if "mediaData" in body and body["mediaData"]:
        offloaded_url, offloaded_path = save_base64_media(body["mediaData"], post_id)
        if offloaded_url:
            fields.append("media_url = ?")
            values.append(offloaded_url)
            fields.append("media_path = ?")
            values.append(offloaded_path)

    if "seedingComments" in body:
        fields.append("seeding_comments = ?")
        values.append(json.dumps(body["seedingComments"], ensure_ascii=False))

    if "autoReplyComments" in body:
        fields.append("auto_reply_comments = ?")
        values.append(json.dumps(body["autoReplyComments"], ensure_ascii=False))

    if "comments" in body:
        fields.append("comments = ?")
        values.append(json.dumps(body["comments"], ensure_ascii=False))

    if "metrics" in body:
        fields.append("metrics = ?")
        values.append(json.dumps(body["metrics"], ensure_ascii=False))

    fields.append("updated_at = ?")
    values.append(now_ms)

    values.append(post_id)
    execute_write(f"UPDATE posts SET {', '.join(fields)} WHERE id = ?", tuple(values))

    add_activity_log("UPDATE_POST", entity_type="post", entity_id=post_id, details={"postId": post_id, "updates": list(body.keys())})

    updated_row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return {"success": True, "post": format_post(updated_row)}

@router.get("/{post_id}/comments")
def get_post_comments(post_id: str):
    """Retrieves comments for a specific post."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    formatted = format_post(existing)
    return {
        "success": True,
        "comments": formatted.get("comments", []),
        "post": formatted
    }

@router.post("/{post_id}/fetch-comments")
def fetch_post_comments(post_id: str):
    """Triggers the Extension to scrape live Facebook comments for this post."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    now_ms = int(time.time() * 1000)
    scheduled_time = now_ms - 2000
    execute_write("""
        UPDATE posts
        SET status = 'pending', scheduled_time = ?, only_action = 'fetch_comments',
            comments = '[]', progress_step = '⚡ Đang quét bình luận trực tiếp từ Facebook...',
            last_error = NULL, updated_at = ?
        WHERE id = ?
    """, (scheduled_time, now_ms, post_id))

    updated_row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return {"success": True, "post": format_post(updated_row)}

@router.post("/{post_id}/comments")
async def sync_or_add_comments(post_id: str, request: Request):
    """Syncs comments array, updates seeding comments, or appends a single comment."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    formatted = format_post(existing)
    existing_comments = formatted.get("comments") or []
    now_ms = int(time.time() * 1000)

    if "comments" in payload and isinstance(payload["comments"], list):
        # Full comments sync
        execute_write(
            "UPDATE posts SET comments = ?, updated_at = ? WHERE id = ?",
            (json.dumps(payload["comments"], ensure_ascii=False), now_ms, post_id)
        )
        return {"success": True, "comments": payload["comments"]}

    elif "seedingComments" in payload and isinstance(payload["seedingComments"], list):
        seeding_list = payload["seedingComments"]
        if "comment" in payload:
            existing_comments.append(payload["comment"])
        execute_write(
            "UPDATE posts SET seeding_comments = ?, comments = ?, updated_at = ? WHERE id = ?",
            (json.dumps(seeding_list, ensure_ascii=False), json.dumps(existing_comments, ensure_ascii=False), now_ms, post_id)
        )
        return {"success": True, "comments": existing_comments, "seedingComments": seeding_list}

    elif "comment" in payload:
        new_cmt = payload["comment"]
        existing_comments.append(new_cmt)
        execute_write(
            "UPDATE posts SET comments = ?, updated_at = ? WHERE id = ?",
            (json.dumps(existing_comments, ensure_ascii=False), now_ms, post_id)
        )
        return {"success": True, "comments": existing_comments}

    raise HTTPException(status_code=400, detail="Invalid payload")

@router.post("/{post_id}/reply-comment")
def reply_comment(post_id: str, payload: ReplyCommentRequest):
    """Posts a reply to a comment and queues the execution for the Extension."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    comment_id = payload.commentId
    reply_text = payload.replyText.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="Nội dung phản hồi không được để trống")

    formatted = format_post(existing)
    existing_comments = formatted.get("comments") or []

    for c in existing_comments:
        if str(c.get("id")) == str(comment_id):
            c["isReplied"] = True

    now_ms = int(time.time() * 1000)
    new_reply = {
        "id": f"reply_{now_ms}",
        "authorName": "Chủ bài viết (Bạn)",
        "text": reply_text,
        "time": now_ms,
        "isSelf": True,
        "parentCommentId": comment_id
    }
    existing_comments.append(new_reply)

    scheduled_time = now_ms - 2000
    progress_step = "🚀 Đang phát lệnh Trả Lời Bình Luận cho Extension ngầm xử lý..."

    execute_write("""
        UPDATE posts
        SET status = 'pending', scheduled_time = ?, only_action = 'reply',
            target_comment_id = ?, auto_reply_comments = ?, comments = ?,
            progress_step = ?, last_error = NULL, last_reply_status = 'pending_execution',
            updated_at = ?
        WHERE id = ?
    """, (
        scheduled_time,
        comment_id,
        json.dumps([reply_text], ensure_ascii=False),
        json.dumps(existing_comments, ensure_ascii=False),
        progress_step,
        now_ms,
        post_id
    ))

    add_activity_log(
        action="REPLY_COMMENT",
        entity_type="post",
        entity_id=post_id,
        details={"postId": post_id, "commentId": comment_id, "replyText": reply_text}
    )

    updated_row = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return {
        "success": True,
        "comment": new_reply,
        "comments": existing_comments,
        "post": format_post(updated_row)
    }

@router.post("/{post_id}/react-comment")
def react_comment(post_id: str, payload: ReactCommentRequest):
    """Sets auto reaction on a comment."""
    existing = query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")

    now_ms = int(time.time() * 1000)
    react_type = payload.reactType or "LOVE"
    comment_id = payload.commentId

    execute_write("""
        UPDATE posts
        SET only_action = 'react', auto_react_type = ?, target_comment_id = ?, updated_at = ?
        WHERE id = ?
    """, (react_type, comment_id, now_ms, post_id))

    add_activity_log(
        action="REACT_COMMENT",
        entity_type="post",
        entity_id=post_id,
        details={"postId": post_id, "commentId": comment_id, "reactType": react_type}
    )

    return {"success": True, "commentId": comment_id, "reactType": react_type}
