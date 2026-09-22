"""
fbauto-backend-python/tests/test_gate2_empirical_challenger2.py
Empirical validation tests for Gate 2 by Challenger 2:
1. Whitespace-only base64: verify no 0-byte physical file created in uploads/.
2. Empty/whitespace content with corrupted media: verify route raises HTTP 400 instead of creating ghost blank posts in DB.
3. Corrupted media variations (garbage chars, bad padding, invalid headers, synthetic corruptions).
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.core.config import settings
from app.services.media_service import save_base64_media
from app.db.session import query_all, query_one, execute_write

client = TestClient(app)

def test_whitespace_base64_no_zero_byte_file_created():
    """Verify that submitting whitespace-only base64 creates NO files on disk at all."""
    files_before = set(os.listdir(settings.UPLOADS_DIR)) if os.path.exists(settings.UPLOADS_DIR) else set()

    whitespace_inputs = [
        " ",
        "   ",
        "\t\t",
        "\n\r\n\t",
        "    \n    ",
        "data:image/png;base64,   ",
        "data:image/png;base64,\n  \t ",
    ]

    for idx, ws in enumerate(whitespace_inputs):
        payload = {
            "base64": ws,
            "fileName": f"whitespace_adversarial_{idx}.png",
            "mimeType": "image/png"
        }
        url, path = save_base64_media(payload, f"emp_ws_{idx}")
        assert url is None, f"Expected url to be None for input {idx}, got {url}"
        assert path is None, f"Expected path to be None for input {idx}, got {path}"

    files_after = set(os.listdir(settings.UPLOADS_DIR)) if os.path.exists(settings.UPLOADS_DIR) else set()
    new_files = files_after - files_before
    assert len(new_files) == 0, f"Leaked 0-byte physical files in uploads/: {new_files}"


def test_post_creation_whitespace_base64_no_disk_leak():
    """Verify HTTP POST /api/posts with whitespace base64 does not create 0-byte files in uploads/."""
    files_before = set(os.listdir(settings.UPLOADS_DIR)) if os.path.exists(settings.UPLOADS_DIR) else set()

    # With non-empty content: should succeed with mediaUrl = "" and NO file written to uploads/
    payload_with_content = {
        "content": "Valid test post with whitespace media",
        "postType": "post",
        "targetType": "profile",
        "mediaData": {
            "base64": "    \t\r\n   ",
            "fileName": "should_never_exist.png",
            "mimeType": "image/png"
        }
    }
    res = client.post("/api/posts", json=payload_with_content)
    assert res.status_code == 201
    post_data = res.json()["post"]
    assert post_data["mediaUrl"] == ""
    assert post_data["mediaPath"] == ""

    # Clean up DB
    execute_write("DELETE FROM posts WHERE id = ?", (post_data["id"],))

    files_after = set(os.listdir(settings.UPLOADS_DIR)) if os.path.exists(settings.UPLOADS_DIR) else set()
    new_files = files_after - files_before
    assert len(new_files) == 0, f"0-byte file created on disk: {new_files}"


def test_empty_content_with_corrupted_media_returns_400():
    """Verify empty content with corrupted media raises HTTP 400 and creates NO ghost post."""
    corrupted_media_payloads = [
        {"base64": "~~~CORRUPTED_BASE64~~~", "fileName": "bad1.png", "mimeType": "image/png"},
        {"base64": "!!!INVALID!!!", "fileName": "bad2.png", "mimeType": "image/png"},
        {"base64": "    ", "fileName": "bad3.png", "mimeType": "image/png"},
        {"base64": "YWJjZGVmZw", "fileName": "bad4.png", "mimeType": "image/png"},  # bad padding
        {"base64": "data:image/png;base64,%%%%CORRUPT%%%%", "fileName": "bad5.png", "mimeType": "image/png"},
    ]

    for idx, bad_media in enumerate(corrupted_media_payloads):
        target_id = f"ghost_test_target_{idx}"
        post_payload = {
            "content": "",
            "postType": "post",
            "targetType": "profile",
            "targetId": target_id,
            "mediaData": bad_media
        }
        res = client.post("/api/posts", json=post_payload)
        assert res.status_code == 400, (
            f"Expected HTTP 400 for corrupted media payload {idx}, got {res.status_code}: {res.text}"
        )
        assert "Invalid media payload" in res.json().get("detail", "") or "không được để trống" in res.json().get("detail", "")

        # Verify NO post was inserted in database
        db_rows = query_all("SELECT * FROM posts WHERE target_id = ?", (target_id,))
        assert len(db_rows) == 0, f"Ghost blank post created in database for test {idx}: {db_rows}"


def test_whitespace_content_with_corrupted_media_returns_400():
    """Verify whitespace-only content with corrupted media raises HTTP 400 and creates NO ghost post."""
    target_id = "ghost_test_ws_content"
    post_payload = {
        "content": "   \n\t  ",
        "postType": "post",
        "targetType": "profile",
        "targetId": target_id,
        "mediaData": {
            "base64": "%%%NOT_BASE64%%%",
            "fileName": "corrupt_ws.png",
            "mimeType": "image/png"
        }
    }
    res = client.post("/api/posts", json=post_payload)
    assert res.status_code == 400, f"Expected HTTP 400, got {res.status_code}: {res.text}"

    db_rows = query_all("SELECT * FROM posts WHERE target_id = ?", (target_id,))
    assert len(db_rows) == 0, f"Ghost blank post created in database: {db_rows}"


def test_no_blank_ghost_posts_exist_in_database():
    """Verify that there are no blank ghost posts in the database."""
    blank_posts = query_all(
        "SELECT id, content, media_url, media_path, status, created_at "
        "FROM posts WHERE (content IS NULL OR TRIM(content) = '') "
        "AND (media_url IS NULL OR TRIM(media_url) = '')"
    )
    assert len(blank_posts) == 0, f"Found blank ghost posts in DB: {blank_posts}"

