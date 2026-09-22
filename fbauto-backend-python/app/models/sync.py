"""
app/models/sync.py
Pydantic V2 schemas for Chrome Extension Sync endpoints (Extension v7.0 compatible).
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

class SyncStatusResponse(BaseModel):
    status: str = "ok"
    version: str = "7.0.0"
    timestamp: int
    service: str = "fbauto-backend-python"

class SyncConfigResponse(BaseModel):
    recaptcha_ent_key: str = "6Ld_sample_key_for_testing"
    recaptcha_action: str = "flow"

class ThemeResponse(BaseModel):
    d: str

class AutoPostReportRequest(BaseModel):
    id: Optional[str] = None
    status: Optional[str] = "completed"
    content: Optional[str] = ""
    postType: Optional[str] = "post"
    targetUrl: Optional[str] = ""
    executionMethod: Optional[str] = None
    fbPostId: Optional[str] = None
    fbPostUrl: Optional[str] = None
    error: Optional[str] = None
