"""Authentication utilities: JWT creation, password hashing, dependency injection."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY

security = HTTPBearer()
AuthCredentials = Annotated[HTTPAuthorizationCredentials, Depends(security)]


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def generate_refresh_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


async def hash_password(password: str) -> str:
    hashed = await _run_bcrypt(bcrypt.hashpw, password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


async def verify_password(password: str, password_hash: str) -> bool:
    return await _run_bcrypt(
        bcrypt.checkpw, password.encode("utf-8"), password_hash.encode("utf-8")
    )


async def _run_bcrypt(func, *args):
    import asyncio
    return await asyncio.to_thread(func, *args)


class TokenData:
    __slots__ = ("user_id",)

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


async def get_current_user(credentials: AuthCredentials) -> TokenData:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload",
            )
        return TokenData(user_id=user_id)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=401,
            detail="Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
