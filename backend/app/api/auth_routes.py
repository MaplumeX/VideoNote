"""Auth routes: register, login, refresh, logout."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import (
    TokenData,
    create_access_token,
    generate_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import REFRESH_TOKEN_EXPIRE_DAYS
from app.db import (
    create_refresh_token,
    create_user,
    get_refresh_token_by_hash,
    get_user_by_email,
    get_user_by_id,
    revoke_all_user_tokens,
    revoke_refresh_token,
)
from app.schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
CurrentUser = Annotated[TokenData, Depends(get_current_user)]

_COOKIE_PATH = "/api/auth/refresh"
_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 86400

_REUSE_MSG = "Token reuse detected — all sessions terminated"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path=_COOKIE_PATH,
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, response: Response):
    existing = await get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    pw_hash = await hash_password(req.password)
    await create_user(user_id, req.email, pw_hash)

    access_token = create_access_token(user_id)
    raw_token, token_hash = generate_refresh_token()
    token_id = str(uuid.uuid4())
    expires_at = (
        datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    await create_refresh_token(token_id, user_id, token_hash, expires_at)

    _set_refresh_cookie(response, raw_token)
    return AuthResponse(access_token=access_token)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, response: Response):
    user = await get_user_by_email(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not await verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id = user["id"]
    access_token = create_access_token(user_id)
    raw_token, token_hash = generate_refresh_token()
    token_id = str(uuid.uuid4())
    expires_at = (
        datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    await create_refresh_token(token_id, user_id, token_hash, expires_at)

    _set_refresh_cookie(response, raw_token)
    return AuthResponse(access_token=access_token)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    record = await get_refresh_token_by_hash(token_hash)

    if not record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if record["revoked_at"] is not None:
        await revoke_all_user_tokens(record["user_id"])
        response.delete_cookie("refresh_token", path=_COOKIE_PATH)
        raise HTTPException(status_code=401, detail=_REUSE_MSG)

    if record["expires_at"] < datetime.now(UTC).isoformat():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Rotate: revoke old token
    revoked = await revoke_refresh_token(token_hash)
    if not revoked:
        await revoke_all_user_tokens(record["user_id"])
        response.delete_cookie("refresh_token", path=_COOKIE_PATH)
        raise HTTPException(status_code=401, detail=_REUSE_MSG)

    # Issue new tokens
    user_id = record["user_id"]
    access_token = create_access_token(user_id)
    new_raw, new_hash = generate_refresh_token()
    token_id = str(uuid.uuid4())
    expires_at = (
        datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    await create_refresh_token(token_id, user_id, new_hash, expires_at)

    _set_refresh_cookie(response, new_raw)
    return AuthResponse(access_token=access_token)


@router.post("/logout")
async def logout(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        await revoke_refresh_token(token_hash)

    response.delete_cookie("refresh_token", path=_COOKIE_PATH)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    db_user = await get_user_by_id(user.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=db_user["id"],
        email=db_user["email"],
        display_name=db_user["display_name"],
    )
