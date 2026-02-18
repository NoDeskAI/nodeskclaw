"""JWT utilities, current_user dependency, KubeConfig AES-256-GCM encryption."""

import base64
import os
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


# ── JWT ──────────────────────────────────────────────────

def create_access_token(
    user_id: str | None = None,
    *,
    subject: str | None = None,
    extra_claims: dict | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    sub = subject or user_id or ""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=settings.JWT_EXPIRE_HOURS))
    payload: dict = {"sub": sub, "exp": expire, "type": "access"}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )


# ── Current User Dependency ──────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header, return User."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证信息")

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 类型错误")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效")

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


# ── KubeConfig AES-256-GCM Encryption ────────────────────

def _get_aes_key() -> bytes:
    """Derive 32-byte AES key from settings."""
    key = settings.ENCRYPTION_KEY.encode("utf-8")
    # Pad or truncate to 32 bytes
    return key[:32].ljust(32, b"0")


def encrypt_kubeconfig(plaintext: str) -> str:
    """Encrypt KubeConfig with AES-256-GCM, return base64(nonce + ciphertext)."""
    key = _get_aes_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_kubeconfig(encrypted: str) -> str:
    """Decrypt base64(nonce + ciphertext) back to KubeConfig plaintext."""
    key = _get_aes_key()
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
