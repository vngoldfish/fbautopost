"""
app/api/routers/logs.py
APIRouter for querying Activity and Audit Logs.
"""

import json
from typing import Optional

from fastapi import APIRouter, Query
from app.db.session import query_all, query_one

router = APIRouter(prefix="/api/logs", tags=["Logs"])

@router.get("")
def get_logs(limit: int = Query(default=100, ge=1, le=500)):
    """Retrieves recent activity logs."""
    total_row = query_one("SELECT count(*) as cnt FROM logs")
    total = total_row["cnt"] if total_row else 0

    rows = query_all("SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,))
    logs = []
    for r in rows:
        details_val = r.get("details")
        if isinstance(details_val, str) and details_val.strip():
            try:
                details = json.loads(details_val)
            except Exception:
                details = {}
        elif isinstance(details_val, dict):
            details = details_val
        else:
            details = {}

        logs.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action": r["action"],
            "details": details
        })

    return {"logs": logs, "total": total}
