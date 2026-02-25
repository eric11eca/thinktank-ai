"""Authentication API routes."""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from src.gateway.auth.jwt import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.gateway.auth.middleware import get_current_user
from src.gateway.auth.models import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.gateway.auth.password import hash_password, verify_password
from src.gateway.auth.user_store import create_user, get_user_by_email
from src.gateway.rate_limiter import check_auth_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _is_production() -> bool:
    """Check if running in production mode."""
    return bool(os.environ.get("REQUIRE_ENV_SECRETS"))


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an httpOnly cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="Create a new user account with email and password.",
)
async def register(request: UserRegisterRequest, response: Response, http_request: Request = None) -> TokenResponse:
    """Register a new user account.

    Args:
        request: Registration data (email, password, optional display_name).
        response: FastAPI response object for setting cookies.

    Returns:
        Access token and user information.

    Raises:
        HTTPException: 409 if email is already registered.
    """
    if http_request:
        check_auth_rate(http_request)
    password_hashed = hash_password(request.password)

    try:
        user = create_user(
            email=request.email,
            password_hash=password_hashed,
            display_name=request.display_name,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    access_token = create_access_token(user["id"], user["email"])
    refresh_token = create_refresh_token(user["id"])
    _set_refresh_cookie(response, refresh_token)

    logger.info(f"New user registered: {user['email']}")

    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticate with email and password.",
)
async def login(request: UserLoginRequest, response: Response, http_request: Request = None) -> TokenResponse:
    """Authenticate a user and return tokens.

    Args:
        request: Login credentials (email, password).
        response: FastAPI response object for setting cookies.

    Returns:
        Access token and user information.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    if http_request:
        check_auth_rate(http_request)
    user = get_user_by_email(request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user["id"], user["email"])
    refresh_token = create_refresh_token(user["id"])
    _set_refresh_cookie(response, refresh_token)

    logger.info(f"User logged in: {user['email']}")

    return TokenResponse(
        access_token=access_token,
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            display_name=user.get("display_name"),
            created_at=user["created_at"],
        ),
    )


@router.post(
    "/refresh",
    response_model=dict,
    summary="Refresh Access Token",
    description="Issue a new access token using the refresh token cookie.",
)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
) -> dict:
    """Refresh the access token using the refresh token cookie.

    Args:
        response: FastAPI response object for setting updated cookies.
        refresh_token: The refresh token from httpOnly cookie.

    Returns:
        New access token.

    Raises:
        HTTPException: 401 if refresh token is missing or invalid.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    try:
        payload = decode_token(refresh_token)
    except Exception:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    from src.gateway.auth.user_store import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    access_token = create_access_token(user["id"], user["email"])

    # Rotate refresh token
    new_refresh_token = create_refresh_token(user["id"])
    _set_refresh_cookie(response, new_refresh_token)

    return {"access_token": access_token}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User",
    description="Return the authenticated user's profile.",
)
async def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> UserResponse:
    """Get the current authenticated user's profile.

    Args:
        current_user: The authenticated user (injected by dependency).

    Returns:
        User profile information.
    """
    return UserResponse(**current_user)


@router.post(
    "/logout",
    summary="Logout",
    description="Clear the refresh token cookie.",
)
async def logout(
    response: Response,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict:
    """Logout by clearing the refresh token cookie.

    Args:
        response: FastAPI response object for clearing cookies.
        current_user: The authenticated user (injected by dependency).

    Returns:
        Success message.
    """
    _clear_refresh_cookie(response)
    logger.info(f"User logged out: {current_user['email']}")
    return {"message": "Logged out successfully"}
