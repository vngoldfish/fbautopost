"""
app/api/routers/settings.py
APIRouter for System Settings (delays, auto-reply templates, sound, notifications).
"""

import time
import json
from typing import Dict, Any

from fastapi import APIRouter, Request
from app.db.session import query_one, execute_write, add_activity_log

router = APIRouter(prefix="/api/settings", tags=["Settings"])

DEFAULT_SETTINGS: Dict[str, Any] = {
    "id": "cfg_main",
    "seedingMinDelay": 3,
    "seedingMaxDelay": 10,
    "autoReplyCheckInterval": 1.0,
    "maxRetries": 3,
    "defaultReactType": "LOVE",
    "defaultReplyTemplates": [
        "Dạ chào bạn, shop đã inbox tư vấn chi tiết cho bạn rồi nhé! ❤️",
        "Cảm ơn bạn đã quan tâm, bạn check tin nhắn giúp shop nhé! ✨"
    ],
    "skipSelfComments": True,
    "showOnScreenBanner": True,
    "enableSounds": False,
    "debugMode": False,
    "apiUrl": "http://localhost:19823"
}

@router.get("")
def get_settings():
    """Retrieves current system settings."""
    row = query_one("SELECT value FROM settings WHERE key = 'cfg_main'")
    if row and row.get("value"):
        try:
            return {"success": True, "settings": json.loads(row["value"])}
        except Exception:
            pass

    # Save defaults if not present
    now_ms = int(time.time() * 1000)
    execute_write(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("cfg_main", json.dumps(DEFAULT_SETTINGS, ensure_ascii=False), now_ms)
    )
    return {"success": True, "settings": DEFAULT_SETTINGS}

@router.post("")
async def update_settings(request: Request):
    """Updates system settings."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    payload["id"] = "cfg_main"
    now_ms = int(time.time() * 1000)
    execute_write(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("cfg_main", json.dumps(payload, ensure_ascii=False), now_ms)
    )
    add_activity_log("SETTINGS_UPDATED", details=payload)
    return {"success": True, "settings": payload}
