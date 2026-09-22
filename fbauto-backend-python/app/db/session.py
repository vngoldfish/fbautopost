"""
app/db/session.py
Thread-Safe Database Session & Transaction Manager for SQLite in WAL Mode.
Provides connection pooling, row mapping, and transaction context managers.
"""

import os
import sqlite3
import threading
import time
import json
import uuid
from datetime import datetime
from typing import Generator, List, Dict, Any, Optional
from contextlib import contextmanager

from app.core.config import settings

# Thread-local storage for per-thread SQLite connections
_local = threading.local()

# Python-level write mutex to cleanly serialize write transactions and prevent busy loops
_write_lock = threading.Lock()

def _create_connection() -> sqlite3.Connection:
    """Creates a new SQLite connection with production WAL pragmas and row factory."""
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(
        settings.DB_PATH,
        timeout=10.0,
        check_same_thread=False,
        isolation_level=None  # Enable autocommit mode so we can explicitly manage BEGIN IMMEDIATE
    )
    conn.row_factory = sqlite3.Row

    # Enforce SQLite WAL pragmas on every connection
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -64000;")  # 64MB memory cache
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

def get_connection() -> sqlite3.Connection:
    """Retrieves or initializes the thread-local SQLite connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _create_connection()
        _local.conn = conn
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database read operations and general queries.
    Usage:
        with get_db() as db:
            rows = db.execute("SELECT * FROM workers").fetchall()
    """
    conn = get_connection()
    try:
        yield conn
    except Exception:
        raise

@contextmanager
def transaction() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for atomic write operations.
    Uses BEGIN IMMEDIATE and _write_lock to guarantee zero deadlocks and zero SQLITE_BUSY errors.
    Automatically commits on normal exit and rolls back on exception.
    Usage:
        with transaction() as db:
            db.execute("UPDATE tasks SET status = ? WHERE id = ?", ("running", task_id))
    """
    conn = get_connection()
    with _write_lock:
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

# ----------------------------------------------------------------------
# Convenience Helper Functions
# ----------------------------------------------------------------------

def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Converts a sqlite3.Row into a standard Python dictionary."""
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    """Converts a list of sqlite3.Row objects into a list of dictionaries."""
    return [dict(r) for r in rows]

def query_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Executes a SELECT query and returns all matching rows as a list of dicts."""
    with get_db() as db:
        cur = db.execute(sql, params)
        return rows_to_list(cur.fetchall())

def query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Executes a SELECT query and returns the first row as a dict, or None."""
    with get_db() as db:
        cur = db.execute(sql, params)
        row = cur.fetchone()
        return row_to_dict(row)

def execute_write(sql: str, params: tuple = ()) -> int:
    """
    Executes an INSERT, UPDATE, or DELETE query within an immediate transaction.
    Returns rowcount.
    """
    with transaction() as db:
        cur = db.execute(sql, params)
        return cur.rowcount

def execute_insert(sql: str, params: tuple = ()) -> Any:
    """
    Executes an INSERT query within an immediate transaction.
    Returns lastrowid.
    """
    with transaction() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid

def execute_script(sql_script: str) -> None:
    """Executes a multi-statement DDL/DML script."""
    with get_db() as db:
        db.executescript(sql_script)

def close_thread_connection() -> None:
    """Closes the current thread's connection (useful during thread cleanup)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None

# FastAPI Route Dependency
def get_db_session() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI route dependency yielding thread-local SQLite connection."""
    with get_db() as db:
        yield db

def add_activity_log(
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    project_key: str = "all",
    details: Optional[Dict[str, Any]] = None
) -> str:
    """Helper to log activity records into logs table with collision-free entropy."""
    now_ms = int(time.time() * 1000)
    entropy = uuid.uuid4().hex[:6]
    log_id = f"log_{now_ms}_{entropy}"
    ts_str = datetime.now().isoformat()
    execute_write(
        "INSERT INTO logs (id, timestamp, action, entity_type, entity_id, project_key, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (log_id, ts_str, action, entity_type, entity_id, project_key, json.dumps(details or {}, ensure_ascii=False), now_ms)
    )
    return log_id

