"""
app/core/middleware.py
Global ASGI/HTTP Middleware for FastAPI:
- CORS Preflight handling
- Whitelist routing (/health, /docs, /admin, /uploads)
- Constant-time X-Sync-Token authentication
- Multi-tenant X-Project-Key validation on worker endpoints
- Tiered sliding-window rate limiting
"""

from typing import Set, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import verify_sync_token, extract_sync_token, extract_project_key
from app.core.rate_limiter import rate_limiter

# Exact paths accessible without authentication or rate limiting
PUBLIC_EXACT_PATHS: Set[str] = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
    "/admin",
    "/admin/",
    "/admin.html",
}

# Path prefixes accessible without authentication
PUBLIC_PREFIXES: Tuple[str, ...] = (
    "/static/",
    "/uploads/",
    "/docs/",
)

# Worker-specific endpoints requiring X-Project-Key
WORKER_REQUIRED_PROJECT_PATHS: Set[str] = {
    "/api/tasks/poll",
    "/api/workers/heartbeat",
    "/api/workers/register",
}

def _add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

async def security_and_rate_limit_middleware(request: Request, call_next):
    # 1. CORS Preflight Bypass (Fast pass for OPTIONS requests)
    if request.method == "OPTIONS":
        response = Response(status_code=204)
        return _add_cors_headers(response)

    path = request.url.path

    # 2. Whitelist Check (Public endpoints bypass auth and rate limiting)
    is_public = (path in PUBLIC_EXACT_PATHS) or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
    if is_public:
        response = await call_next(request)
        return _add_cors_headers(response)

    # Resolve Client IP (handling reverse proxy X-Forwarded-For headers)
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )

    # 3. Tiered Sliding-Window Rate Limiting
    if settings.RATE_LIMIT_ENABLED:
        if path in ("/api/tasks/poll", "/api/workers/heartbeat"):
            tier_limit = settings.RATE_LIMIT_POLL_PER_MIN
            tier_key = f"{client_ip}:poll"
        elif request.method in ("POST", "PUT") and path in ("/api/posts", "/api/tasks"):
            tier_limit = settings.RATE_LIMIT_CREATION_PER_MIN
            tier_key = f"{client_ip}:create"
        else:
            tier_limit = settings.RATE_LIMIT_GENERAL_PER_MIN
            tier_key = f"{client_ip}:general"

        allowed, retry_after = rate_limiter.is_allowed(tier_key, limit=tier_limit)
        if not allowed:
            resp = JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": "Rate limit exceeded. Please back off.",
                    "retryAfterSec": retry_after
                }
            )
            return _add_cors_headers(resp)

    # 4. Token Authentication (X-Sync-Token enforcement)
    if settings.SYNC_TOKEN:
        token = extract_sync_token(request)
        if not verify_sync_token(token):
            resp = JSONResponse(
                status_code=401,
                content={"error": "Unauthorized: Invalid or missing X-Sync-Token"}
            )
            return _add_cors_headers(resp)

    # 5. Worker Project Key Validation (Multi-tenant partition enforcement)
    if path in WORKER_REQUIRED_PROJECT_PATHS:
        project_key = extract_project_key(request)
        if not project_key or not project_key.strip():
            resp = JSONResponse(
                status_code=400,
                content={"error": "Missing X-Project-Key header"}
            )
            return _add_cors_headers(resp)

    # Proceed to router
    response = await call_next(request)
    return _add_cors_headers(response)
