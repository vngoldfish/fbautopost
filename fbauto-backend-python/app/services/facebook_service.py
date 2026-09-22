"""
app/services/facebook_service.py
Facebook Graph API integration service for publishing posts, photos, videos, reels, and stories.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any

from app.core.config import settings
from app.db.session import add_activity_log

def publish_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """Attempts to publish a post via Facebook Graph API if accessToken & targetId are present."""
    try:
        post_type = post.get("postType") or post.get("post_type") or "post"
        access_token = post.get("accessToken") or post.get("access_token")
        target_id = post.get("targetId") or post.get("target_id")
        post_id = post.get("id", "")

        if access_token and target_id:
            add_activity_log(
                action="FB_POST_ATTEMPT",
                entity_type="post",
                entity_id=post_id,
                details={
                    "postId": post_id,
                    "postType": post_type,
                    "content": (post.get("content") or "")[:50]
                }
            )
            return publish_via_graph_api(post, target_id, access_token)

        # No access token -> Chrome Extension browser automation post
        return {
            "success": False,
            "isExtensionPost": True,
            "error": "Chờ Chrome Extension thực thi trên Facebook web"
        }
    except Exception as e:
        add_activity_log(
            action="FB_POST_FAILED",
            entity_type="post",
            entity_id=post.get("id", ""),
            details={"postId": post.get("id"), "error": str(e)}
        )
        return {"success": False, "error": str(e)}

def publish_via_graph_api(post: Dict[str, Any], target_id: str, access_token: str) -> Dict[str, Any]:
    """Publishes directly to Facebook using official Graph API endpoints."""
    try:
        post_type = post.get("postType") or post.get("post_type") or "post"
        media_url = post.get("mediaUrl") or post.get("media_url")
        content = post.get("content") or ""

        if post_type == "video":
            endpoint = f"{settings.FB_GRAPH_API_URL}/{target_id}/videos"
            data = {"description": content, "access_token": access_token}
            if media_url:
                data["file_url"] = media_url
        elif post_type == "reel":
            endpoint = f"{settings.FB_GRAPH_API_URL}/{target_id}/video_reels"
            data = {"description": content, "access_token": access_token}
            if media_url:
                data["video_url"] = media_url
        elif post_type == "story":
            endpoint = f"{settings.FB_GRAPH_API_URL}/{target_id}/photo_stories"
            data = {"caption": content, "access_token": access_token}
            if media_url:
                data["url"] = media_url
        else:  # Regular post or photo
            endpoint = f"{settings.FB_GRAPH_API_URL}/{target_id}/photos" if media_url else f"{settings.FB_GRAPH_API_URL}/{target_id}/feed"
            data = {"message": content, "access_token": access_token}
            if media_url:
                data["url"] = media_url

        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(endpoint, data=encoded_data, method="POST")

        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            result = json.loads(res_body)
            return {
                "success": True,
                "publishedAt": datetime.now().isoformat(),
                "postId": result.get("id") or result.get("post_id") or result.get("video_id"),
                "postType": post_type,
                "rawResponse": result
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
