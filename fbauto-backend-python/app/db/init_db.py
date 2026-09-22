"""
app/db/init_db.py
Database Schema Initializer & JSON Migration Script.
Creates relational tables, configures SQLite WAL mode, deduplicates accounts,
and offloads Base64 media into uploads/ storage.
"""

import os
import sys
import json
import time
import base64
import sqlite3
import re
from typing import Dict, Any, List, Optional

# Path resolution
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(CURRENT_DIR) == "db":
    APP_DIR = os.path.dirname(CURRENT_DIR)
    BACKEND_DIR = os.path.dirname(APP_DIR)
else:
    BACKEND_DIR = CURRENT_DIR

DATA_DIR = os.path.join(BACKEND_DIR, "data")
UPLOADS_DIR = os.path.join(BACKEND_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "fbauto.db")

DDL_STATEMENTS = """
-- ====================================================================
-- FB AUTO POST PRODUCTION DATABASE SCHEMA (SQLite 3.40+ WAL MODE)
-- ====================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;

-- 1. Projects
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 2. Workers
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    project_key TEXT DEFAULT 'all',
    status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('idle', 'busy', 'paused', 'error', 'offline', 'online')),
    ip_address TEXT DEFAULT '',
    extension_version TEXT DEFAULT '',
    last_heartbeat INTEGER NOT NULL,
    current_task_id TEXT,
    assigned_accounts TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workers_status_heartbeat ON workers(status, last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_workers_project ON workers(project_key);

-- 3. Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'profile' CHECK (account_type IN ('profile', 'page', 'group', 'user')),
    project_key TEXT DEFAULT 'all',
    worker_id TEXT,
    access_token TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'checkpoint', 'expired', 'logged_out')),
    cookie_status TEXT DEFAULT 'valid' CHECK (cookie_status IN ('valid', 'invalid', 'expired', 'unknown')),
    daily_post_count INTEGER DEFAULT 0,
    daily_action_count INTEGER DEFAULT 0,
    last_action_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_target_id ON accounts(target_id);
CREATE INDEX IF NOT EXISTS idx_accounts_worker ON accounts(worker_id);
CREATE INDEX IF NOT EXISTS idx_accounts_project ON accounts(project_key);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);

-- 4. Posts
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    project_key TEXT DEFAULT 'all',
    post_type TEXT NOT NULL DEFAULT 'post' CHECK (post_type IN ('post', 'video', 'reel', 'story')),
    content TEXT,
    target_type TEXT NOT NULL DEFAULT 'profile' CHECK (target_type IN ('profile', 'page', 'group', 'user')),
    target_url TEXT,
    target_id TEXT,
    actor_id TEXT,
    access_token TEXT,
    media_url TEXT,
    media_path TEXT,
    seeding_comments TEXT DEFAULT '[]',
    auto_reply_comments TEXT DEFAULT '[]',
    auto_react_type TEXT DEFAULT 'NONE' CHECK (auto_react_type IN ('NONE', 'LIKE', 'LOVE', 'HAHA', 'WOW', 'SAD', 'ANGRY')),
    metrics TEXT DEFAULT '{"likes": 0, "comments": 0, "shares": 0}',
    scheduled_time INTEGER NOT NULL,
    repeat_interval_minutes INTEGER DEFAULT 0,
    source TEXT DEFAULT 'api',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'in_progress', 'completed', 'failed', 'cancelled')),
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,
    progress_step TEXT,
    executed_at INTEGER,
    execution_method TEXT,
    fb_post_id TEXT,
    fb_post_url TEXT,
    comments TEXT DEFAULT '[]',
    only_action TEXT,
    target_comment_id TEXT,
    last_reply_status TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_status_time ON posts(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_posts_project ON posts(project_key);
CREATE INDEX IF NOT EXISTS idx_posts_target_id ON posts(target_id);

-- 5. Tasks (Distributed Task Queue)
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL CHECK (task_type IN ('post', 'seed', 'warmup', 'reply_comment', 'react_comment', 'fetch_comments')),
    project_key TEXT DEFAULT 'all',
    worker_id TEXT,
    account_id TEXT,
    post_id TEXT,
    priority INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'running', 'completed', 'failed', 'cancelled')),
    payload TEXT NOT NULL,
    scheduled_time INTEGER NOT NULL,
    claimed_at INTEGER,
    lease_expires_at INTEGER,
    completed_at INTEGER,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,
    result_data TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_poll ON tasks(status, scheduled_time, priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_worker_status ON tasks(worker_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_lease ON tasks(status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_post_id ON tasks(post_id);

-- 6. Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 7. Activity Logs
CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    project_key TEXT DEFAULT 'all',
    details TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_action ON logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_entity ON logs(entity_type, entity_id);

-- 8. Targets (Discovered Pages & Groups)
CREATE TABLE IF NOT EXISTS targets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_type TEXT NOT NULL,
    raw_data TEXT DEFAULT '{}',
    updated_at INTEGER NOT NULL
);

-- 9. Tokens (Extension Sync)
CREATE TABLE IF NOT EXISTS tokens (
    id TEXT PRIMARY KEY,
    request_id TEXT,
    token TEXT,
    error TEXT,
    user_agent TEXT,
    received_at INTEGER NOT NULL
);
"""

def load_json_file(filename: str) -> Any:
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to read {filename}: {e}")
        return []

def init_database(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL_STATEMENTS)
    conn.commit()
    return conn

def migrate_projects(conn: sqlite3.Connection):
    projects_data = load_json_file("projects.json")
    project_map: Dict[str, dict] = {}

    if isinstance(projects_data, list):
        for p in projects_data:
            if isinstance(p, dict) and p.get("id"):
                project_map[p["id"]] = p

    # Ensure default system projects exist
    if "default" not in project_map:
        project_map["default"] = {
            "id": "default",
            "name": "Dự án Mặc Định (Default)",
            "description": "Dự án hệ thống mặc định",
            "createdAt": int(time.time() * 1000)
        }
    if "taikhoan1" not in project_map:
        project_map["taikhoan1"] = {
            "id": "taikhoan1",
            "name": "Tài khoản 1 (taikhoan1)",
            "description": "Dự án / Extension 1",
            "createdAt": int(time.time() * 1000)
        }

    now_ms = int(time.time() * 1000)
    for p in project_map.values():
        created_at = p.get("createdAt") or now_ms
        conn.execute("""
            INSERT OR REPLACE INTO projects (id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (p["id"], p.get("name", p["id"]), p.get("description", ""), created_at, now_ms))

    conn.commit()
    print(f"[*] Projects migrated: {len(project_map)}")

def migrate_accounts(conn: sqlite3.Connection):
    raw_accounts = load_json_file("accounts.json")
    if not isinstance(raw_accounts, list):
        return

    # Deduplicate accounts by targetId, keeping latest by createdAt
    dedup: Dict[str, dict] = {}
    for acc in raw_accounts:
        if not isinstance(acc, dict):
            continue
        tid = str(acc.get("targetId") or "").strip()
        if not tid:
            continue
        created = acc.get("createdAt", 0)
        if tid not in dedup or created > dedup[tid].get("createdAt", 0):
            dedup[tid] = acc

    now_ms = int(time.time() * 1000)
    for tid, acc in dedup.items():
        acc_id = acc.get("id") or f"acc_{int(time.time()*1000)}"
        acc_type = acc.get("type", "profile")
        if acc_type not in ["profile", "page", "group", "user"]:
            acc_type = "profile"
        created_at = acc.get("createdAt") or now_ms

        conn.execute("""
            INSERT OR REPLACE INTO accounts (
                id, target_id, name, account_type, project_key, worker_id,
                access_token, status, cookie_status, daily_post_count,
                daily_action_count, last_action_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            acc_id,
            tid,
            acc.get("name") or f"Account {tid}",
            acc_type,
            acc.get("projectKey") or "all",
            acc.get("workerId"),
            acc.get("accessToken") or "",
            acc.get("status") or "active",
            acc.get("cookieStatus") or "valid",
            acc.get("dailyPostCount", 0),
            acc.get("dailyActionCount", 0),
            acc.get("lastActionAt"),
            created_at,
            now_ms
        ))

    conn.commit()
    print(f"[*] Accounts migrated: raw={len(raw_accounts)} -> deduplicated={len(dedup)}")

def migrate_posts(conn: sqlite3.Connection):
    posts_data = load_json_file("posts.json")
    if not isinstance(posts_data, list):
        return

    now_ms = int(time.time() * 1000)
    migrated_count = 0

    for p in posts_data:
        if not isinstance(p, dict) or not p.get("id"):
            continue

        post_id = p["id"]
        media_url = p.get("mediaUrl") or ""
        media_path = p.get("mediaPath") or None
        media_data = p.get("mediaData")

        # Media offloading pipeline: extract Base64 data to physical file
        if media_data:
            b64_str = ""
            file_name = f"{post_id}_media.bin"
            if isinstance(media_data, dict):
                b64_str = media_data.get("base64") or ""
                file_name = media_data.get("fileName") or file_name
            elif isinstance(media_data, str):
                b64_str = media_data

            if b64_str:
                # Handle data URI header if present
                if "," in b64_str and ";base64" in b64_str:
                    header, b64_content = b64_str.split(",", 1)
                    b64_str = b64_content

                try:
                    raw_bytes = base64.b64decode(b64_str)
                    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(file_name))
                    if not os.path.splitext(clean_name)[1]:
                        clean_name += ".png"
                    target_file = f"{post_id}_{clean_name}"
                    abs_file_path = os.path.join(UPLOADS_DIR, target_file)

                    with open(abs_file_path, "wb") as mf:
                        mf.write(raw_bytes)

                    media_path = f"uploads/{target_file}"
                    media_url = f"/uploads/{target_file}"
                    print(f"    [Media] Offloaded {len(raw_bytes)} bytes for post {post_id} -> {media_path}")
                except Exception as e:
                    print(f"[WARN] Error decoding media for {post_id}: {e}")

        created_at = p.get("createdAt") or now_ms
        post_type = p.get("postType") or "post"
        if post_type not in ["post", "video", "reel", "story"]:
            post_type = "post"

        target_type = p.get("targetType") or "profile"
        if target_type not in ["profile", "page", "group", "user"]:
            target_type = "profile"

        status = p.get("status") or "pending"
        if status not in ["pending", "running", "in_progress", "completed", "failed", "cancelled"]:
            status = "pending"

        conn.execute("""
            INSERT OR REPLACE INTO posts (
                id, project_key, post_type, content, target_type, target_url,
                target_id, actor_id, access_token, media_url, media_path,
                seeding_comments, auto_reply_comments, auto_react_type,
                metrics, scheduled_time, repeat_interval_minutes, source,
                status, retry_count, max_retries, last_error, progress_step,
                executed_at, execution_method, fb_post_id, fb_post_url,
                comments, only_action, target_comment_id, last_reply_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            p.get("projectKey") or "all",
            post_type,
            p.get("content") or "",
            target_type,
            p.get("targetUrl") or "",
            p.get("targetId") or "",
            p.get("actorId") or "",
            p.get("accessToken") or "",
            media_url,
            media_path,
            json.dumps(p.get("seedingComments") or [], ensure_ascii=False),
            json.dumps(p.get("autoReplyComments") or [], ensure_ascii=False),
            p.get("autoReactType") or "NONE",
            json.dumps(p.get("metrics") or {"likes": 0, "comments": 0, "shares": 0}),
            p.get("scheduledTime") or now_ms,
            p.get("repeatIntervalMinutes") or 0,
            p.get("source") or "api",
            status,
            p.get("retryCount") or 0,
            p.get("maxRetries") or 3,
            p.get("lastError"),
            p.get("progressStep"),
            p.get("executedAt"),
            p.get("executionMethod"),
            p.get("fbPostId"),
            p.get("fbPostUrl"),
            json.dumps(p.get("comments") or [], ensure_ascii=False),
            p.get("onlyAction"),
            p.get("targetCommentId"),
            p.get("lastReplyStatus"),
            created_at,
            now_ms
        ))
        migrated_count += 1

    conn.commit()
    print(f"[*] Posts migrated: {migrated_count}")

def migrate_settings(conn: sqlite3.Connection):
    settings_data = load_json_file("settings.json")
    now_ms = int(time.time() * 1000)

    default_cfg = {
        "id": "cfg_main",
        "seedingMinDelay": 3,
        "seedingMaxDelay": 10,
        "autoReplyCheckInterval": 1.0,
        "maxRetries": 3,
        "defaultReactType": "LOVE",
        "defaultReplyTemplates": [
            "Dạ chào bạn, shop đã inbox tư vấn chi tiết cho bạn rồi nhé! ❤️",
            "Cảm ơn bạn đã quan tâm, bạn check tin nhắn giúp shop nhé! ✨"
        ],
        "skipSelfComments": True,
        "showOnScreenBanner": True,
        "enableSounds": False,
        "debugMode": False,
        "apiUrl": "http://localhost:19823"
    }

    if isinstance(settings_data, list) and len(settings_data) > 0 and isinstance(settings_data[0], dict):
        cfg = settings_data[0]
        key = cfg.get("id") or "cfg_main"
        conn.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(cfg, ensure_ascii=False), now_ms))
    elif isinstance(settings_data, dict) and settings_data:
        key = settings_data.get("id") or "cfg_main"
        conn.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(settings_data, ensure_ascii=False), now_ms))
    else:
        conn.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        """, ("cfg_main", json.dumps(default_cfg, ensure_ascii=False), now_ms))

    conn.commit()
    print("[*] Settings migrated")

def migrate_logs(conn: sqlite3.Connection):
    logs_data = load_json_file("logs.json")
    if not isinstance(logs_data, list):
        return

    migrated = 0
    for log in logs_data:
        if not isinstance(log, dict):
            continue
        log_id = log.get("id") or f"log_{int(time.time()*1000)}"
        ts_str = log.get("timestamp") or ""
        created_at = int(time.time() * 1000)
        if "log_" in log_id:
            try:
                created_at = int(log_id.split("_")[1])
            except Exception:
                pass

        details = log.get("details") or {}
        conn.execute("""
            INSERT OR IGNORE INTO logs (
                id, timestamp, action, entity_type, entity_id, project_key, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log_id,
            ts_str,
            log.get("action") or "UNKNOWN",
            details.get("entityType"),
            details.get("postId") or details.get("accId"),
            "all",
            json.dumps(details, ensure_ascii=False),
            created_at
        ))
        migrated += 1

    conn.commit()
    print(f"[*] Logs migrated: {migrated}")

def migrate_targets(conn: sqlite3.Connection):
    targets_data = load_json_file("targets.json")
    now_ms = int(time.time() * 1000)

    if isinstance(targets_data, list):
        for t in targets_data:
            if isinstance(t, dict) and t.get("id"):
                conn.execute("""
                    INSERT OR REPLACE INTO targets (id, name, target_type, raw_data, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    t["id"],
                    t.get("name") or t["id"],
                    t.get("type") or "page",
                    json.dumps(t, ensure_ascii=False),
                    now_ms
                ))
        conn.commit()
        print(f"[*] Targets migrated: {len(targets_data)}")

def migrate_tokens(conn: sqlite3.Connection):
    tokens_data = load_json_file("tokens.json")
    if isinstance(tokens_data, list):
        for tok in tokens_data:
            if isinstance(tok, dict) and tok.get("id"):
                conn.execute("""
                    INSERT OR IGNORE INTO tokens (id, request_id, token, error, user_agent, received_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    tok["id"],
                    tok.get("requestId"),
                    tok.get("token"),
                    tok.get("error"),
                    tok.get("userAgent"),
                    tok.get("receivedAt") or int(time.time() * 1000)
                ))
        conn.commit()

def run_migration():
    print("=== Starting FB Auto Post Database Initialization & Migration ===")
    conn = init_database()
    try:
        migrate_projects(conn)
        migrate_accounts(conn)
        migrate_posts(conn)
        migrate_settings(conn)
        migrate_logs(conn)
        migrate_targets(conn)
        migrate_tokens(conn)

        # Verification report
        print("\n=== Post-Migration Database Integrity Report ===")
        for table in ["projects", "accounts", "posts", "tasks", "workers", "settings", "logs", "targets", "tokens"]:
            cnt = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"  Table '{table}': {cnt} records")
        print("=== Database Migration Completed Successfully ===")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
