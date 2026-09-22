"""
app/api/deps.py
Shared FastAPI dependencies for authentication, multi-tenancy, and database access.
"""

from app.db.session import get_db_session
from app.core.security import require_sync_token, require_project_key, get_worker_identity, WorkerIdentity

__all__ = [
    "get_db_session",
    "require_sync_token",
    "require_project_key",
    "get_worker_identity",
    "WorkerIdentity"
]
