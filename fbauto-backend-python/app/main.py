"""
app/main.py
Central FastAPI Application Factory for fbAUTO SaaS Engine.
Wires lifespan hooks, security/rate-limiting middleware, routers, uploads static files,
and SaaS Admin Console frontend.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.middleware import security_and_rate_limit_middleware
from app.db.init_db import init_database, run_migration
from app.services import scheduler_service

from app.api.routers import (
    health,
    posts,
    accounts,
    projects,
    settings as settings_router,
    logs,
    sync,
    workers,
    tasks,
    ai
)

_admin_html_cache = None
_admin_html_mtime = 0

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Application startup & shutdown lifespan."""
    print("[INFO] Initializing fbAUTO Database & WAL mode...")
    init_database()
    run_migration()

    print("[INFO] Starting background post scheduler...")
    scheduler_service.start_scheduler(15)

    yield

    print("[INFO] Shutting down background scheduler...")
    scheduler_service.stop_scheduler()

def create_app() -> FastAPI:
    """Factory function for FastAPI application."""
    app = FastAPI(
        title="fbAUTO SaaS Engine",
        description="Production Facebook Account Farm & Automation Management Platform",
        version="2.0.0",
        lifespan=lifespan
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Security, Rate Limiting & Multi-Tenant Middleware
    app.middleware("http")(security_and_rate_limit_middleware)

    # 3. Mount Static Uploads Directory
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")

    # 4. Include Modular Routers
    app.include_router(health.router)
    app.include_router(posts.router)
    app.include_router(accounts.router)
    app.include_router(projects.router)
    app.include_router(settings_router.router)
    app.include_router(logs.router)
    app.include_router(sync.router)
    app.include_router(workers.router)
    app.include_router(tasks.router)
    app.include_router(ai.router)

    # 5. Admin Console Web Routes
    @app.get("/", response_class=HTMLResponse)
    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/", response_class=HTMLResponse)
    @app.get("/admin.html", response_class=HTMLResponse)
    def serve_admin_console():
        global _admin_html_cache, _admin_html_mtime
        admin_path = settings.ADMIN_HTML_PATH
        if not os.path.exists(admin_path):
            return HTMLResponse("<h3>Admin console file not found</h3>", status_code=404)

        try:
            mtime = os.path.getmtime(admin_path)
            if _admin_html_cache is None or mtime > _admin_html_mtime:
                with open(admin_path, "r", encoding="utf-8") as f:
                    _admin_html_cache = f.read()
                _admin_html_mtime = mtime

            return HTMLResponse(
                content=_admin_html_cache,
                status_code=200,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    return app

app = create_app()
