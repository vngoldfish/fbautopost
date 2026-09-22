"""
app/models/task.py
Pydantic V2 schemas for Distributed Task Queue Engine.
Supports multi-alias validation (taskType/type, workerId/id, accountId/targetAccountId).
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class TaskPollRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    workerId: str = Field(..., description="Worker node ID polling for tasks")
    projectKey: Optional[str] = None
    supportedTypes: Optional[List[str]] = Field(
        default_factory=lambda: ["post", "seed", "warmup", "reply_comment"]
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "workerId" not in data and "id" in data:
                data["workerId"] = data["id"]
            if "supportedTypes" not in data and "types" in data:
                data["supportedTypes"] = data["types"]
        return data

    @property
    def id(self) -> str:
        """Compatibility property accessor."""
        return self.workerId


class TaskStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    workerId: Optional[str] = Field(default=None, description="Worker node ID reporting status")
    status: Optional[str] = None  # completed | failed | running
    progressStep: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "workerId" not in data and "id" in data:
                data["workerId"] = data["id"]
        return data

    @property
    def id(self) -> str:
        """Compatibility property accessor."""
        return self.workerId


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: Optional[str] = None
    taskType: str = Field(
        default="post",
        description="Task kind: post | seed | warmup | reply_comment | react_comment | fetch_comments"
    )
    projectKey: Optional[str] = "all"
    workerId: Optional[str] = None
    accountId: Optional[str] = None
    postId: Optional[str] = None
    priority: Optional[int] = 0
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    scheduledTime: Optional[int] = None
    maxRetries: Optional[int] = 3

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "taskType" not in data and "type" in data:
                data["taskType"] = data["type"]
            if "accountId" not in data and "targetAccountId" in data:
                data["accountId"] = data["targetAccountId"]
            if "maxRetries" not in data and "max_retries" in data:
                data["maxRetries"] = data["max_retries"]
        return data

    @property
    def type(self) -> str:
        """Compatibility property accessor."""
        return self.taskType


class TaskPollResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    task: Optional[Dict[str, Any]] = None
