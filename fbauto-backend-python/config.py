"""
fbauto-backend-python/config.py
Legacy configuration proxy.
Redirects to app.core.config.settings to preserve backward compatibility.
"""

import os
from app.core.config import settings

PORT = settings.PORT
HOST = settings.HOST
SYNC_TOKEN = settings.SYNC_TOKEN
THEME_VER = settings.THEME_VER
BASE_DIR = settings.BASE_DIR
DATA_DIR = settings.DATA_DIR
UPLOADS_DIR = settings.UPLOADS_DIR
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
FB_GRAPH_API_URL = settings.FB_GRAPH_API_URL
