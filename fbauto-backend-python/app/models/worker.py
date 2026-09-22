"""
app/models/worker.py
Pydantic V2 schemas for Extension Worker Nodes (Registration, Heartbeat, Monitoring, Account Assignment).
Supports multi-alias validation (workerId/id, version/extensionVersion, currentTaskId/activeTaskId).
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class WorkerRegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    workerId: str = Field(..., description="Unique identifier of the extension worker node")
    name: Optional[str] = None
    projectKey: Optional[str] = "all"
    version: Optional[str] = Field(default="7.0.0", description="Extension semantic version")
    assignedAccounts: Optional[List[str]] = Field(default_factory=list)
    userAgent: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "workerId" not in data and "id" in data:
                data["workerId"] = data["id"]
            if "version" not in data and "extensionVersion" in data:
                data["version"] = data["extensionVersion"]
            if "assignedAccounts" not in data and "accounts" in data:
                data["assignedAccounts"] = data["accounts"]
        return data

    @property
    def id(self) -> str:
        """Compatibility property accessor."""
        return self.workerId


class WorkerHeartbeatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    workerId: str = Field(..., description="Unique identifier of the extension worker node")
    projectKey: Optional[str] = None
    status: Optional[str] = "idle"  # idle | busy | paused | error | online
    currentTaskId: Optional[str] = Field(default=None, description="Currently executing task ID, if any")
    accounts: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "workerId" not in data and "id" in data:
                data["workerId"] = data["id"]
            if "currentTaskId" not in data and "activeTaskId" in data:
                data["currentTaskId"] = data["activeTaskId"]
        return data

    @property
    def id(self) -> str:
        """Compatibility property accessor."""
        return self.workerId

    @property
    def activeTaskId(self) -> Optional[str]:
        """Compatibility property accessor."""
        return self.currentTaskId


class WorkerAccountAssignRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    accountIds: Optional[List[str]] = Field(default_factory=list)
    accountId: Optional[str] = None
    assignedAccounts: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_account_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "accountIds" not in data or data["accountIds"] is None:
                if "accountId" in data and data["accountId"]:
                    data["accountIds"] = [str(data["accountId"]).strip()]
                elif "assignedAccounts" in data and data["assignedAccounts"] is not None:
                    data["accountIds"] = [str(x).strip() for x in data["assignedAccounts"]]
                elif "accounts" in data and data["accounts"] is not None:
                    data["accountIds"] = [str(x).strip() for x in data["accounts"]]
                else:
                    data["accountIds"] = []
            elif isinstance(data["accountIds"], list):
                data["accountIds"] = [str(x).strip() for x in data["accountIds"]]
        return data


class WorkerRegisterResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    status: str = "ok"
    workerId: str
    config: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "workerId" not in data and "id" in data:
                data["workerId"] = data["id"]
        return data


class WorkerHeartbeatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    status: str = "ok"
    timestamp: int
    hasPendingTasks: bool = False
