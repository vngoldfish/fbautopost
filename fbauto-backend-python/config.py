import os

PORT = int(os.environ.get("PORT", 19823))
HOST = os.environ.get("HOST", "0.0.0.0")
SYNC_TOKEN = os.environ.get("SYNC_TOKEN", "")
THEME_VER = 0x5A

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
POSTS_FILE = os.path.join(DATA_DIR, "posts.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")

FB_GRAPH_API_URL = "https://graph.facebook.com/v19.0"

