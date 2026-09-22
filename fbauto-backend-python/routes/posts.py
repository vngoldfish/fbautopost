import time
import random
import string
from datetime import datetime
import database

def handle_posts_route(path: str, method: str, body: dict = None, query: dict = None) -> tuple:
    # GET /api/posts
    if path == "/api/posts" and method == "GET":
        posts = database.get_collection("posts")
        status = query.get("status") if query else None
        post_type = query.get("postType") or query.get("type") if query else None
        if status and status != "all":
            posts = [p for p in posts if p.get("status") == status]
        if post_type and post_type != "all":
            posts = [p for p in posts if p.get("postType") == post_type]
        return 200, {"posts": posts, "total": len(posts)}

    # GET /api/posts/<id>
    if path.startswith("/api/posts/") and not path.endswith("/run-now") and not path.endswith("/comments") and method == "GET":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if found:
            return 200, {"success": True, "post": found}
        return 404, {"error": "Post not found"}

    # POST /api/posts
    if path == "/api/posts" and method == "POST":
        payload = body or {}
        content = payload.get("content", "")
        post_type = payload.get("postType") or payload.get("type") or "post"
        if post_type not in ["post", "video", "reel", "story"]:
            post_type = "post"

        if not content and not payload.get("mediaUrl") and not payload.get("mediaData"):
            return 400, {"error": "Nội dung, URL Media hoặc File đính kèm không được để trống"}

        scheduled_time_raw = payload.get("scheduledTime")
        post_time = int(time.time() * 1000)
        if scheduled_time_raw:
            try:
                post_time = int(scheduled_time_raw)
            except (ValueError, TypeError):
                try:
                    dt = datetime.fromisoformat(str(scheduled_time_raw))
                    post_time = int(dt.timestamp() * 1000)
                except Exception:
                    post_time = int(time.time() * 1000)

        rand_str = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
        try:
            repeat_interval = int(payload.get("repeatIntervalMinutes") or 0)
        except (ValueError, TypeError):
            repeat_interval = 0

        new_post = {
            "id": f"post_{int(time.time() * 1000)}_{rand_str}",
            "postType": post_type, # post | video | reel | story
            "content": content,
            "targetType": payload.get("targetType", "profile"), # profile | page | group
            "targetUrl": payload.get("targetUrl", ""),
            "targetId": payload.get("targetId", ""),
            "actorId": payload.get("actorId", ""), # Page ID if posting as Fanpage
            "accessToken": payload.get("accessToken", ""),
            "mediaUrl": payload.get("mediaUrl", ""),
            "mediaData": payload.get("mediaData", None),
            "seedingComments": payload.get("seedingComments", []), # Array of comments to seed
            "autoReplyComments": payload.get("autoReplyComments", []), # Array of auto-reply texts
            "autoReactType": payload.get("autoReactType", "NONE"), # NONE | LIKE | LOVE | HAHA | WOW
            "metrics": payload.get("metrics", {"likes": 0, "comments": 0, "shares": 0}),
            "scheduledTime": post_time,
            "repeatIntervalMinutes": repeat_interval,
            "source": payload.get("source", "api"),
            "status": "pending",
            "retryCount": 0,
            "maxRetries": 3,
            "lastError": None,
            "createdAt": int(time.time() * 1000)
        }

        database.insert_item("posts", new_post)
        database.add_log("CREATE_POST", {"postId": new_post["id"], "postType": post_type, "scheduledTime": new_post["scheduledTime"]})
        return 201, {"success": True, "post": new_post}

    # DELETE /api/posts/<id>
    if path.startswith("/api/posts/") and method == "DELETE":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        deleted = database.delete_item("posts", post_id)
        if deleted:
            database.add_log("DELETE_POST", {"postId": post_id})
            return 200, {"success": True, "id": post_id}
        return 404, {"error": "Post not found"}

    # POST /api/posts/<id>/run-now -> Force execute post now
    if path.startswith("/api/posts/") and path.endswith("/run-now") and method == "POST":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        req_body = body or {}
        action = req_body.get("action")
        
        updates = {
            "status": "pending",
            "scheduledTime": int(time.time() * 1000) - 2000,
            "progressStep": f"🚀 Đang phát lệnh [{action or 'POST'}] cho Extension xử lý...",
            "lastError": None
        }
        if action:
            updates["onlyAction"] = action
        
        updated = database.update_item("posts", post_id, updates)
        if updated:
            database.add_log("TRIGGER_POST_NOW", {"postId": post_id, "action": action})
            return 200, {"success": True, "post": updated}
        return 404, {"error": "Post not found"}

    # PUT / PATCH /api/posts/<id>
    if path.startswith("/api/posts/") and method in ["PUT", "PATCH"]:
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        updates = body or {}
        updated = database.update_item("posts", post_id, updates)
        if updated:
            database.add_log("UPDATE_POST", {"postId": post_id, "updates": updates})
            return 200, {"success": True, "post": updated}
        return 404, {"error": "Post not found"}

    # GET /api/posts/<id>/comments
    if path.startswith("/api/posts/") and path.endswith("/comments") and method == "GET":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if found:
            return 200, {"success": True, "comments": found.get("comments", []), "post": found}
        return 404, {"error": "Post not found"}

    # POST /api/posts/<id>/fetch-comments -> Force extension to query live Facebook comments immediately
    if path.startswith("/api/posts/") and path.endswith("/fetch-comments") and method == "POST":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if not found:
            return 404, {"error": "Post not found"}

        updates = {
            "status": "pending",
            "scheduledTime": int(time.time() * 1000) - 2000,
            "onlyAction": "fetch_comments",
            "comments": [],  # Reset old cached database comments before live scan
            "progressStep": "⚡ Đang quét bình luận trực tiếp từ Facebook...",
            "lastError": None
        }
        database.update_item("posts", post_id, updates)
        found.update(updates)
        return 200, {"success": True, "post": found}

    # POST /api/posts/<id>/comments -> Sync or add comment
    if path.startswith("/api/posts/") and path.endswith("/comments") and method == "POST":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if not found:
            return 404, {"error": "Post not found"}

        payload = body or {}
        existing_comments = found.get("comments", [])
        
        if "comments" in payload and isinstance(payload["comments"], list):
            # Sync full comments list
            updated = database.update_item("posts", post_id, {"comments": payload["comments"]})
            return 200, {"success": True, "comments": payload["comments"]}
        elif "seedingComments" in payload and isinstance(payload["seedingComments"], list):
            # Explicit seedingComments list provided: overwrite seeding list (prevents 1:2:3 accumulation on test clicks)
            seeding_list = payload["seedingComments"]
            existing_comments = found.get("comments", [])
            if "comment" in payload:
                existing_comments.append(payload["comment"])
            database.update_item("posts", post_id, {
                "seedingComments": seeding_list,
                "comments": existing_comments
            })
            return 200, {"success": True, "comments": existing_comments, "seedingComments": seeding_list}
        elif "comment" in payload:
            # Add single comment without modifying seeding list
            new_cmt = payload["comment"]
            existing_comments.append(new_cmt)
            database.update_item("posts", post_id, {
                "comments": existing_comments
            })
            return 200, {"success": True, "comments": existing_comments}
        
        return 400, {"error": "Invalid payload"}

    # POST /api/posts/<id>/reply-comment -> Reply to a specific comment
    if path.startswith("/api/posts/") and path.endswith("/reply-comment") and method == "POST":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if not found:
            return 404, {"error": "Post not found"}

        payload = body or {}
        comment_id = payload.get("commentId", "")
        reply_text = payload.get("replyText", "")
        if not reply_text:
            return 400, {"error": "Nội dung phản hồi không được để trống"}

        existing_comments = found.get("comments", [])
        for c in existing_comments:
            if str(c.get("id")) == str(comment_id):
                c["isReplied"] = True

        new_reply = {
            "id": f"reply_{int(time.time() * 1000)}",
            "authorName": "Chủ bài viết (Bạn)",
            "text": reply_text,
            "time": int(time.time() * 1000),
            "isSelf": True,
            "parentCommentId": comment_id
        }
        existing_comments.append(new_reply)
        
        updates = {
            "status": "pending",
            "scheduledTime": int(time.time() * 1000) - 2000,
            "onlyAction": "reply",
            "targetCommentId": comment_id,
            "autoReplyComments": [reply_text],
            "comments": existing_comments,
            "progressStep": "🚀 Đang phát lệnh Trả Lời Bình Luận cho Extension ngầm xử lý...",
            "lastError": None,
            "lastReplyStatus": "pending_execution"
        }
        database.update_item("posts", post_id, updates)
        database.add_log("REPLY_COMMENT", {"postId": post_id, "commentId": comment_id, "replyText": reply_text})
        found.update(updates)
        return 200, {"success": True, "comment": new_reply, "comments": existing_comments, "post": found}

    # POST /api/posts/<id>/react-comment -> React to a specific comment/post
    if path.startswith("/api/posts/") and path.endswith("/react-comment") and method == "POST":
        parts = [p for p in path.split('/') if p]
        post_id = parts[2] if len(parts) > 2 else ""
        posts = database.get_collection("posts")
        found = next((p for p in posts if p.get("id") == post_id), None)
        if not found:
            return 404, {"error": "Post not found"}

        payload = body or {}
        comment_id = payload.get("commentId", "")
        react_type = payload.get("reactType", "LOVE")

        updates = {
            "onlyAction": "react",
            "autoReactType": react_type
        }
        database.update_item("posts", post_id, updates)
        database.add_log("REACT_COMMENT", {"postId": post_id, "commentId": comment_id, "reactType": react_type})
        return 200, {"success": True, "commentId": comment_id, "reactType": react_type}

    return 404, {"error": "Post Route not found"}

