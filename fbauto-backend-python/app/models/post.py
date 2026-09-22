"""
app/models/post.py
Pydantic V2 schemas for Facebook Posts, Comments, Seeding, and Reactions.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

class CommentItem(BaseModel):
    id: Optional[str] = None
    authorName: Optional[str] = "Khách hàng"
    text: str
    time: Optional[int] = None
    isSelf: Optional[bool] = False
    parentCommentId: Optional[str] = None
    isReplied: Optional[bool] = False

class PostCreateRequest(BaseModel):
    postType: Optional[str] = Field("post", description="post | video | reel | story")
    type: Optional[str] = None  # Legacy alias
    content: Optional[str] = ""
    targetType: Optional[str] = "profile"  # profile | page | group | user
    targetUrl: Optional[str] = ""
    targetId: Optional[str] = ""
    actorId: Optional[str] = ""
    accessToken: Optional[str] = ""
    mediaUrl: Optional[str] = ""
    mediaData: Optional[Any] = None  # Base64 string or dict from client
    seedingComments: Optional[List[str]] = Field(default_factory=list)
    autoReplyComments: Optional[List[str]] = Field(default_factory=list)
    autoReactType: Optional[str] = "NONE"  # NONE | LIKE | LOVE | HAHA | WOW | SAD | ANGRY
    metrics: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"likes": 0, "comments": 0, "shares": 0})
    scheduledTime: Optional[Union[int, str]] = None
    repeatIntervalMinutes: Optional[Union[int, str]] = 0
    projectKey: Optional[str] = None
    project: Optional[str] = None  # Legacy alias
    source: Optional[str] = "api"

class PostUpdateRequest(BaseModel):
    content: Optional[str] = None
    postType: Optional[str] = None
    targetType: Optional[str] = None
    targetUrl: Optional[str] = None
    targetId: Optional[str] = None
    actorId: Optional[str] = None
    accessToken: Optional[str] = None
    status: Optional[str] = None
    scheduledTime: Optional[Union[int, str]] = None
    repeatIntervalMinutes: Optional[Union[int, str]] = None
    mediaUrl: Optional[str] = None
    mediaData: Optional[Any] = None
    seedingComments: Optional[List[str]] = None
    autoReplyComments: Optional[List[str]] = None
    autoReactType: Optional[str] = None
    progressStep: Optional[str] = None
    executionMethod: Optional[str] = None
    fbPostId: Optional[str] = None
    fbPostUrl: Optional[str] = None
    lastError: Optional[str] = None
    comments: Optional[List[Dict[str, Any]]] = None
    onlyAction: Optional[str] = None
    targetCommentId: Optional[str] = None
    lastReplyStatus: Optional[str] = None

class RunNowRequest(BaseModel):
    action: Optional[str] = None  # POST | reply | react | fetch_comments

class SyncCommentRequest(BaseModel):
    comments: Optional[List[Dict[str, Any]]] = None
    seedingComments: Optional[List[str]] = None
    comment: Optional[Dict[str, Any]] = None

class ReplyCommentRequest(BaseModel):
    commentId: str
    replyText: str

class ReactCommentRequest(BaseModel):
    commentId: str
    reactType: Optional[str] = "LOVE"

class PostResponse(BaseModel):
    success: bool = True
    post: Optional[Dict[str, Any]] = None

class PostListResponse(BaseModel):
    posts: List[Dict[str, Any]]
    total: int
