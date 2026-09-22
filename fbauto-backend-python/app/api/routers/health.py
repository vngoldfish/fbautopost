"""
app/api/routers/health.py
Healthcheck endpoint for Docker, VPS, and load balancers.
"""

from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter(tags=["Health"])

@router.get("/health")
def healthcheck() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "engine": "FastAPI",
        "version": "2.0.0"
    }
