"""
app/models/account.py
Pydantic V2 schemas for Facebook Accounts, Health Status, and Discovered Targets.
Supports health status updates (live, checkpoint, expired, locked) and general updates.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class AccountCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: Optional[str] = None
    name: str
    accessToken: str
    type: Optional[str] = "page"  # profile | page | group | user
    targetId: Optional[str] = ""
    projectKey: Optional[str] = "all"
    workerId: Optional[str] = None


class AccountHealthRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    healthStatus: Optional[str] = None
    status: Optional[str] = None
    checkpointType: Optional[str] = None
    checkpointMessage: Optional[str] = None
    message: Optional[str] = None
    detectedAt: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # message <-> checkpointMessage
            if "message" in data and ("checkpointMessage" not in data or not data["checkpointMessage"]):
                data["checkpointMessage"] = data["message"]
            elif "checkpointMessage" in data and ("message" not in data or not data["message"]):
                data["message"] = data["checkpointMessage"]

            # healthStatus <-> status
            if "healthStatus" not in data and "status" in data:
                data["healthStatus"] = data["status"]
            elif "status" not in data and "healthStatus" in data:
                data["status"] = data["healthStatus"]
        return data


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = None
    healthStatus: Optional[str] = None
    status: Optional[str] = None
    cookieStatus: Optional[str] = None
    workerId: Optional[str] = None
    projectKey: Optional[str] = None
    accessToken: Optional[str] = None
    checkpointType: Optional[str] = None
    checkpointMessage: Optional[str] = None
    message: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "message" in data and ("checkpointMessage" not in data or not data["checkpointMessage"]):
                data["checkpointMessage"] = data["message"]
            if "healthStatus" not in data and "status" in data:
                data["healthStatus"] = data["status"]
            elif "status" not in data and "healthStatus" in data:
                data["status"] = data["healthStatus"]
        return data


class TargetSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    targets: List[Dict[str, Any]]


class AccountResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    success: bool = True
    account: Optional[Dict[str, Any]] = None


class AccountListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    accounts: List[Dict[str, Any]]
    total: int
