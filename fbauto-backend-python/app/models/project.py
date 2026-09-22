"""
app/models/project.py
Pydantic V2 schemas for Project multi-tenancy grouping.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class ProjectCreateRequest(BaseModel):
    id: Optional[str] = None
    projectKey: Optional[str] = None
    key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = ""

class ProjectResponse(BaseModel):
    success: bool = True
    project: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class ProjectListResponse(BaseModel):
    projects: List[Dict[str, Any]]
    total: int
