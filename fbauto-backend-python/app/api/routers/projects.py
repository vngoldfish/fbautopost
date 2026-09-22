"""
app/api/routers/projects.py
APIRouter for Project Multi-Tenancy Management.
"""

import time
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, status, Request
from app.db.session import query_all, query_one, execute_write, add_activity_log
from app.models.project import ProjectCreateRequest

router = APIRouter(prefix="/api/projects", tags=["Projects"])

def format_project(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "description": row.get("description") or "",
        "createdAt": row.get("created_at")
    }

@router.get("")
def list_projects():
    """Retrieves all defined tenant projects."""
    rows = query_all("SELECT * FROM projects ORDER BY created_at ASC")
    projects = [format_project(r) for r in rows]
    return {"projects": projects, "total": len(projects)}

@router.post("")
@router.put("")
def create_or_upsert_project(payload: ProjectCreateRequest):
    """Creates or updates a project via atomic SQLite upsert."""
    project_id = (payload.id or payload.projectKey or payload.key or "").strip().lower()
    project_name = (payload.name or project_id).strip()
    description = payload.description or ""

    if not project_id:
        raise HTTPException(status_code=400, detail="Mã project (projectKey) không được để trống")

    now_ms = int(time.time() * 1000)

    execute_write("""
        INSERT INTO projects (id, name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            updated_at = excluded.updated_at
    """, (project_id, project_name, description, now_ms, now_ms))

    saved = query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    is_created = saved and saved["created_at"] == now_ms
    msg = f"Đã tạo mới project {project_id}" if is_created else f"Đã cập nhật project {project_id}"

    add_activity_log("SAVE_PROJECT", entity_type="project", entity_id=project_id, details={"name": project_name})
    return {"success": True, "project": format_project(saved), "message": msg}

@router.put("/{project_id}")
def update_project_by_id(project_id: str, payload: ProjectCreateRequest):
    """Updates a project by URL ID parameter via atomic SQLite upsert."""
    p_id = project_id.strip().lower()
    project_name = (payload.name or p_id).strip()
    description = payload.description or ""

    now_ms = int(time.time() * 1000)

    execute_write("""
        INSERT INTO projects (id, name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            updated_at = excluded.updated_at
    """, (p_id, project_name, description, now_ms, now_ms))

    saved = query_one("SELECT * FROM projects WHERE id = ?", (p_id,))
    is_created = saved and saved["created_at"] == now_ms
    msg = f"Đã tạo mới project {p_id}" if is_created else f"Đã cập nhật project {p_id}"

    add_activity_log("UPDATE_PROJECT", entity_type="project", entity_id=p_id, details={"name": project_name})
    return {"success": True, "project": format_project(saved), "message": msg}

@router.delete("/{project_id}")
def delete_project(project_id: str):
    """Deletes a project."""
    p_id = project_id.strip().lower()
    existing = query_one("SELECT id FROM projects WHERE id = ?", (p_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy project {p_id}")

    execute_write("DELETE FROM projects WHERE id = ?", (p_id,))
    add_activity_log("DELETE_PROJECT", entity_type="project", entity_id=p_id)
    return {"success": True, "message": f"Đã xóa project {p_id}"}
