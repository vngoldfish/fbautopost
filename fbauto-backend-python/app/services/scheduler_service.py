"""
app/services/scheduler_service.py
Background scheduler thread that polls the SQLite database for:
1. Pending scheduled posts and dispatches them via the Facebook Graph API.
2. Zombie tasks with expired leases (Watchdog) and reclaims or marks them failed.
"""

import time
import threading
from typing import Dict, Any, Optional

from app.db.session import query_all, execute_write, add_activity_log
from app.services import facebook_service

_worker_thread = None
_stop_event = threading.Event()

def start_scheduler(interval_sec: int = 15):
    """Starts the background scheduler thread."""
    global _worker_thread, _stop_event
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_run_worker, args=(interval_sec,), daemon=True)
    _worker_thread.start()
    print(f"[INFO] Python Scheduler Worker started (interval: {interval_sec}s)")

def stop_scheduler():
    """Signals the background scheduler thread to gracefully stop."""
    global _stop_event
    _stop_event.set()
    print("[INFO] Python Scheduler Worker stopped")

def _run_worker(interval_sec: int):
    while not _stop_event.is_set():
        try:
            process_scheduled_posts()
        except Exception as e:
            print(f"[ERROR] Error in python scheduler loop (posts): {e}")

        try:
            reclaim_zombie_tasks()
        except Exception as e:
            print(f"[ERROR] Error in python scheduler loop (zombie watchdog): {e}")

        _stop_event.wait(interval_sec)

def reclaim_zombie_tasks(now_ms: Optional[int] = None) -> int:
    """
    Scans SQLite for tasks where status is 'running' or 'assigned' and lease_expires_at < now_ms.
    If retry_count < max_retries:
        Reclaims the task by resetting status = 'pending', clearing worker_id & lease_expires_at,
        incrementing retry_count, and logging TASK_LEASE_RECLAIMED.
    If retry_count >= max_retries:
        Sets status = 'failed', clears lease_expires_at, records error = 'Lease expired and max retries exceeded',
        and logs TASK_LEASE_EXPIRED_FAILED.
    Returns the count of processed zombie tasks.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    zombies = query_all(
        "SELECT * FROM tasks WHERE status IN ('running', 'assigned') "
        "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
        (now_ms,)
    )

    processed_count = 0
    for task in zombies:
        task_id = task["id"]
        retry_count = task.get("retry_count") or 0
        max_retries = task.get("max_retries")
        if max_retries is None:
            max_retries = 3

        prev_worker = task.get("worker_id")

        if retry_count < max_retries:
            new_retry = retry_count + 1
            execute_write(
                "UPDATE tasks SET status = 'pending', worker_id = NULL, lease_expires_at = NULL, "
                "retry_count = ?, updated_at = ? WHERE id = ?",
                (new_retry, now_ms, task_id)
            )
            if prev_worker:
                execute_write(
                    "UPDATE workers SET current_task_id = NULL, updated_at = ? "
                    "WHERE id = ? AND current_task_id = ?",
                    (now_ms, prev_worker, task_id)
                )

            add_activity_log(
                "TASK_LEASE_RECLAIMED",
                entity_type="task",
                entity_id=task_id,
                project_key=task.get("project_key") or "all",
                details={
                    "taskId": task_id,
                    "retryCount": new_retry,
                    "maxRetries": max_retries,
                    "previousWorkerId": prev_worker
                }
            )
        else:
            execute_write(
                "UPDATE tasks SET status = 'failed', lease_expires_at = NULL, "
                "last_error = 'Lease expired and max retries exceeded', updated_at = ? WHERE id = ?",
                (now_ms, task_id)
            )
            if prev_worker:
                execute_write(
                    "UPDATE workers SET current_task_id = NULL, updated_at = ? "
                    "WHERE id = ? AND current_task_id = ?",
                    (now_ms, prev_worker, task_id)
                )

            add_activity_log(
                "TASK_LEASE_EXPIRED_FAILED",
                entity_type="task",
                entity_id=task_id,
                project_key=task.get("project_key") or "all",
                details={
                    "taskId": task_id,
                    "retryCount": retry_count,
                    "maxRetries": max_retries,
                    "error": "Lease expired and max retries exceeded"
                }
            )

        processed_count += 1

    return processed_count

def process_scheduled_posts():
    """Queries for due posts and processes Graph API posts."""
    now_ms = int(time.time() * 1000)

    # Only query posts that have an accessToken (Graph API automated posts)
    # Posts without accessToken are executed by Chrome Extension Workers
    due_posts = query_all(
        "SELECT * FROM posts WHERE status = 'pending' AND scheduled_time <= ? "
        "AND access_token IS NOT NULL AND access_token != ''",
        (now_ms,)
    )

    for post in due_posts:
        post_id = post["id"]
        content = post.get("content") or ""
        print(f"[Scheduler] Executing Post [{post_id}]: '{content[:40]}...'")

        # Mark in progress
        execute_write("UPDATE posts SET status = 'in_progress' WHERE id = ?", (post_id,))

        result = facebook_service.publish_post(post)

        if result.get("success"):
            fb_post_id = result.get("postId") or ""
            repeat_min = post.get("repeat_interval_minutes") or 0

            if repeat_min > 0:
                new_scheduled_time = now_ms + (repeat_min * 60000)
                execute_write(
                    "UPDATE posts SET status = 'pending', scheduled_time = ?, executed_at = ?, "
                    "last_error = NULL, fb_post_id = ? WHERE id = ?",
                    (new_scheduled_time, now_ms, fb_post_id, post_id)
                )
            else:
                execute_write(
                    "UPDATE posts SET status = 'completed', executed_at = ?, "
                    "last_error = NULL, fb_post_id = ? WHERE id = ?",
                    (now_ms, fb_post_id, post_id)
                )

            add_activity_log("SCHEDULED_POST_SUCCESS", entity_type="post", entity_id=post_id, details={"postId": post_id, "fbPostId": fb_post_id})

        elif result.get("isExtensionPost"):
            # Reset to pending for extension
            execute_write(
                "UPDATE posts SET status = 'pending', scheduled_time = ?, last_error = NULL WHERE id = ?",
                (now_ms + 10000, post_id)
            )
            add_activity_log("AWAITING_EXTENSION", entity_type="post", entity_id=post_id, details={"postId": post_id})

        else:
            retry_count = (post.get("retry_count") or 0) + 1
            max_retries = post.get("max_retries") or 3
            err_msg = str(result.get("error") or "Unknown error")

            if retry_count >= max_retries:
                execute_write(
                    "UPDATE posts SET status = 'failed', retry_count = ?, last_error = ? WHERE id = ?",
                    (retry_count, err_msg, post_id)
                )
            else:
                retry_time = now_ms + 60000  # retry in 1 minute
                execute_write(
                    "UPDATE posts SET status = 'pending', scheduled_time = ?, retry_count = ?, last_error = ? WHERE id = ?",
                    (retry_time, retry_count, err_msg, post_id)
                )

            add_activity_log(
                "SCHEDULED_POST_RETRY",
                entity_type="post",
                entity_id=post_id,
                details={"postId": post_id, "retryCount": retry_count, "error": err_msg}
            )
