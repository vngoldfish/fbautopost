import os
import json
import time
from datetime import datetime
import threading
import config

_db_lock = threading.RLock()

# Ensure data directory exists
os.makedirs(config.DATA_DIR, exist_ok=True)

FILES = {
    "posts": config.POSTS_FILE,
    "tokens": config.TOKENS_FILE,
    "logs": config.LOGS_FILE,
    "targets": os.path.join(config.DATA_DIR, "targets.json"),
    "accounts": os.path.join(config.DATA_DIR, "accounts.json"),
    "settings": os.path.join(config.DATA_DIR, "settings.json"),
    "projects": os.path.join(config.DATA_DIR, "projects.json")
}

# Initialize empty JSON files
for key, file_path in FILES.items():
    if not os.path.exists(file_path):
        default_data = []
        if key == "projects":
            default_data = [
                {"id": "taikhoan1", "name": "Tài khoản 1 (taikhoan1)", "description": "Dự án / Extension 1", "createdAt": int(time.time() * 1000)},
                {"id": "taikhoan2", "name": "Tài khoản 2 (taikhoan2)", "description": "Dự án / Extension 2", "createdAt": int(time.time() * 1000)}
            ]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)

def get_collection(name: str) -> list:
    with _db_lock:
        file_path = FILES.get(name)
        if not file_path or not os.path.exists(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

def save_collection(name: str, data: list):
    with _db_lock:
        file_path = FILES.get(name)
        if not file_path:
            return
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)

def insert_item(name: str, item: dict) -> dict:
    with _db_lock:
        items = get_collection(name)
        items.append(item)
        save_collection(name, items)
        return item

def update_item(name: str, item_id: str, updates: dict) -> dict:
    with _db_lock:
        items = get_collection(name)
        for i, item in enumerate(items):
            if item.get("id") == item_id:
                items[i].update(updates)
                save_collection(name, items)
                return items[i]
        return None

def delete_item(name: str, item_id: str) -> bool:
    with _db_lock:
        items = get_collection(name)
        initial_len = len(items)
        items = [i for i in items if i.get("id") != item_id]
        save_collection(name, items)
        return len(items) < initial_len

def add_log(action: str, details: dict = None) -> dict:
    with _db_lock:
        logs = get_collection("logs")
        log_entry = {
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details or {}
        }
        logs.append(log_entry)
        logs = logs[-500:]
        save_collection("logs", logs)
        return log_entry
