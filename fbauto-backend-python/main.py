"""
fbauto-backend-python/main.py
Root entrypoint proxy for fbAUTO Python backend.
Imports the modular FastAPI application from app.main:app.
"""

import sys
import os

# Ensure the backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app
from app.core.config import settings
import uvicorn

if __name__ == "__main__":
    print(f"[START] Starting fbAUTO Production Server on http://{settings.HOST}:{settings.PORT}")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
