"""
app/core/security.py
Cryptographic authentication and authorization dependencies for FastAPI.
Enforces X-Sync-Token, X-Project-Key, and X-Worker-Id headers.
Provides constant-time verification and XOR theme crypto.
"""

import hmac
from typing import Optional
from fastapi import Request, HTTPException, status
from app.core.config import settings

def verify_sync_token(provided_token: Optional[str]) -> bool:
    """
    Constant-time comparison between provided token and server SYNC_TOKEN.
    If SYNC_TOKEN is not configured (empty), allow access (development mode).
    """
    if not settings.SYNC_TOKEN:
        return True
    if not provided_token:
        return False
    return hmac.compare_digest(
        provided_token.strip().encode("utf-8"),
        settings.SYNC_TOKEN.strip().encode("utf-8")
    )

def extract_sync_token(request: Request) -> Optional[str]:
    """
    Extract token from headers (X-Sync-Token, RFC 6750 Authorization: Bearer) or query string fallback.
    """
    token = request.headers.get("X-Sync-Token") or request.headers.get("x-sync-token")
    if not token:
        auth = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        token = request.query_params.get("token") or request.query_params.get("sync_token")
    return token

def extract_project_key(request: Request) -> Optional[str]:
    """
    Extract tenant project key from headers or query string.
    """
    return (
        request.headers.get("X-Project-Key")
        or request.headers.get("x-project-key")
        or request.query_params.get("projectKey")
        or request.query_params.get("project_key")
    )

def extract_worker_id(request: Request) -> Optional[str]:
    """
    Extract worker identifier from headers (supports legacy X-Ext-Id as fallback).
    """
    return (
        request.headers.get("X-Worker-Id")
        or request.headers.get("x-worker-id")
        or request.headers.get("X-Ext-Id")
        or request.headers.get("x-ext-id")
        or request.query_params.get("workerId")
    )

# --- FastAPI Route Dependencies ---

async def require_sync_token(request: Request) -> str:
    """
    FastAPI Dependency: Ensures caller possesses valid X-Sync-Token.
    """
    token = extract_sync_token(request)
    if not verify_sync_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-Sync-Token",
            headers={"WWW-Authenticate": "Bearer, X-Sync-Token"}
        )
    return token or ""

async def require_project_key(request: Request) -> str:
    """
    FastAPI Dependency: Ensures caller provides non-empty X-Project-Key.
    """
    project_key = extract_project_key(request)
    if not project_key or not project_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Project-Key header"
        )
    return project_key.strip()

class WorkerIdentity:
    def __init__(self, worker_id: str, project_key: str):
        self.worker_id = worker_id
        self.project_key = project_key

async def get_worker_identity(request: Request) -> WorkerIdentity:
    """
    FastAPI Dependency: Validates and extracts both workerId and projectKey.
    """
    worker_id = extract_worker_id(request)
    if not worker_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Worker-Id header"
        )
    project_key = await require_project_key(request)
    return WorkerIdentity(worker_id=worker_id, project_key=project_key)

# --- XOR Theme Crypto (compatible with Extension v7.0) ---

def parse_theme(hex_string: str) -> str:
    """Decrypts XOR 0x5A hex string received from Extension."""
    if not hex_string:
        return ""
    result = []
    for i in range(0, len(hex_string), 2):
        byte_val = int(hex_string[i:i+2], 16)
        result.append(chr(byte_val ^ settings.THEME_VER))
    return "".join(result)

def serialize_theme(plaintext: str) -> str:
    """Encrypts plaintext into XOR 0x5A hex string for Extension."""
    if not plaintext:
        return ""
    encoded_chars = []
    for char in plaintext:
        code = ord(char)
        if code > 127:
            encoded_chars.append(f"\\u{code:04x}")
        else:
            encoded_chars.append(char)
    ascii_str = "".join(encoded_chars)
    result = []
    for char in ascii_str:
        result.append(f"{(ord(char) ^ settings.THEME_VER):02x}")
    return "".join(result)
