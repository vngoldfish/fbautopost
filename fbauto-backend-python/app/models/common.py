"""
app/models/common.py
Common response wrappers, status enums, and base schemas.
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

class BaseResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[Any] = None
