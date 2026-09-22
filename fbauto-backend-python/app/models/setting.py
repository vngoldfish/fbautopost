"""
app/models/setting.py
Pydantic V2 schemas for System Settings.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class SystemSettingsModel(BaseModel):
    id: str = "cfg_main"
    seedingMinDelay: int = 3
    seedingMaxDelay: int = 10
    autoReplyCheckInterval: float = 1.0
    maxRetries: int = 3
    defaultReactType: str = "LOVE"
    defaultReplyTemplates: List[str] = Field(default_factory=lambda: [
        "Dạ chào bạn, shop đã inbox tư vấn chi tiết cho bạn rồi nhé! ❤️",
        "Cảm ơn bạn đã quan tâm, bạn check tin nhắn giúp shop nhé! ✨"
    ])
    skipSelfComments: bool = True
    showOnScreenBanner: bool = True
    enableSounds: bool = False
    debugMode: bool = False
    apiUrl: str = "http://localhost:19823"

class SettingsResponse(BaseModel):
    success: bool = True
    settings: Dict[str, Any]
