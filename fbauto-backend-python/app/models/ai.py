"""
app/models/ai.py
Pydantic V2 schemas for AI Smart Suggestion endpoints.
"""

from typing import Optional
from pydantic import BaseModel

class AiSuggestReplyRequest(BaseModel):
    commentText: Optional[str] = ""
    postContent: Optional[str] = ""
    tone: Optional[str] = "friendly"

class AiSuggestReplyResponse(BaseModel):
    success: bool = True
    suggestedReply: str
    commentText: str
    tone: str
