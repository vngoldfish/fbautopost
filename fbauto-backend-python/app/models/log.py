"""
app/models/log.py
Pydantic V2 schemas for System and Activity Logs.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class LogEntry(BaseModel):
    id: str
    timestamp: str
    action: str
    details: Optional[Dict[str, Any]] = None

class LogListResponse(BaseModel):
    logs: List[Dict[str, Any]]
    total: int
