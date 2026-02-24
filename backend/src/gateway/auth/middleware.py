"""FastAPI authentication dependencies."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.gateway.auth.jwt import decode_token
from src.gateway.auth.user_store import get_user_by_id

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=True)
_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> dict[str, Any]:
    """FastAPI dependency that extracts and verifies a JWT access token.

    Returns the user dict (id, email, display_name, created_at) on success.
    Raises 401 on any failure.
    """
    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": user["created_at"],
    }


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme_optional)
    ],
) -> dict[str, Any] | None:
    """FastAPI dependency that optionally extracts a JWT access token.

    Returns the user dict if a valid token is present, or None if no token
    is provided. Useful for backward compatibility with Electron mode.
    """
    if credentials is None:
        return None

    try:
        payload = decode_token(credentials.credentials)
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = get_user_by_id(user_id)
    if not user:
        return None

    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": user["created_at"],
    }
