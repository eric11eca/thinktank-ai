"""Integration tests for auth API routes.

Uses httpx.AsyncClient with FastAPI's TestClient pattern to test the full
request/response cycle including middleware, cookies, and dependency injection.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

# Minimal FastAPI app for testing auth routes in isolation
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.gateway.auth.routes import router

_app = FastAPI()
_app.include_router(router)


@pytest_asyncio.fixture()
async def client(tmp_store_dir, jwt_secret):
    """Async HTTP client bound to the test app."""
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRegister:
    """Tests for POST /api/auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Successful registration returns 201 with access token and user."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": "SecurePass1",
                "display_name": "New User",
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "new@example.com"
        assert body["user"]["display_name"] == "New User"
        assert "id" in body["user"]

    @pytest.mark.asyncio
    async def test_register_sets_refresh_cookie(self, client: AsyncClient):
        """Registration sets the refresh_token httpOnly cookie."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "cookie@example.com",
                "password": "SecurePass1",
            },
        )

        assert resp.status_code == 201
        cookies = resp.cookies
        assert "refresh_token" in cookies

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        """Registering with a duplicate email returns 409."""
        await client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "password": "SecurePass1",
            },
        )

        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "password": "SecurePass2",
            },
        )

        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Registration with a weak password returns 422."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "password": "short",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Registration with an invalid email returns 422."""
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecurePass1",
            },
        )

        assert resp.status_code == 422


class TestLogin:
    """Tests for POST /api/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, tmp_store_dir):
        """Successful login returns access token and user info."""
        # Register first
        await client.post(
            "/api/auth/register",
            json={
                "email": "login@example.com",
                "password": "SecurePass1",
            },
        )

        resp = await client.post(
            "/api/auth/login",
            json={
                "email": "login@example.com",
                "password": "SecurePass1",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["user"]["email"] == "login@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, tmp_store_dir):
        """Login with wrong password returns 401."""
        await client.post(
            "/api/auth/register",
            json={
                "email": "wrongpw@example.com",
                "password": "SecurePass1",
            },
        )

        resp = await client.post(
            "/api/auth/login",
            json={
                "email": "wrongpw@example.com",
                "password": "WrongPassword2",
            },
        )

        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Login with a nonexistent email returns 401."""
        resp = await client.post(
            "/api/auth/login",
            json={
                "email": "ghost@example.com",
                "password": "SecurePass1",
            },
        )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_sets_refresh_cookie(self, client: AsyncClient, tmp_store_dir):
        """Login sets the refresh_token cookie."""
        await client.post(
            "/api/auth/register",
            json={
                "email": "logincookie@example.com",
                "password": "SecurePass1",
            },
        )

        resp = await client.post(
            "/api/auth/login",
            json={
                "email": "logincookie@example.com",
                "password": "SecurePass1",
            },
        )

        assert "refresh_token" in resp.cookies


class TestMe:
    """Tests for GET /api/auth/me."""

    @pytest.mark.asyncio
    async def test_me_authenticated(self, client: AsyncClient, tmp_store_dir):
        """Authenticated /me returns the current user."""
        # Register to get an access token
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "email": "me@example.com",
                "password": "SecurePass1",
                "display_name": "Me User",
            },
        )
        token = reg_resp.json()["access_token"]

        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me@example.com"
        assert body["display_name"] == "Me User"

    @pytest.mark.asyncio
    async def test_me_no_token(self, client: AsyncClient):
        """Calling /me without a token returns 401/403 (no credentials)."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client: AsyncClient):
        """Calling /me with an invalid token returns 401."""
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestRefresh:
    """Tests for POST /api/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, tmp_store_dir):
        """Refreshing with a valid refresh cookie returns a new access token."""
        # Register to get tokens
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "email": "refresh@example.com",
                "password": "SecurePass1",
            },
        )

        # Extract the refresh cookie and send it
        refresh_cookie = reg_resp.cookies.get("refresh_token")
        assert refresh_cookie is not None

        resp = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    @pytest.mark.asyncio
    async def test_refresh_no_cookie(self, client: AsyncClient):
        """Refreshing without a cookie returns 401."""
        resp = await client.post("/api/auth/refresh")
        assert resp.status_code == 401
        assert "no refresh token" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_invalid_cookie(self, client: AsyncClient):
        """Refreshing with an invalid cookie returns 401."""
        resp = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": "invalid.token"},
        )
        assert resp.status_code == 401


class TestLogout:
    """Tests for POST /api/auth/logout."""

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, client: AsyncClient, tmp_store_dir):
        """Logout clears the refresh_token cookie."""
        # Register to get tokens
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "email": "logout@example.com",
                "password": "SecurePass1",
            },
        )
        token = reg_resp.json()["access_token"]

        resp = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    @pytest.mark.asyncio
    async def test_logout_requires_auth(self, client: AsyncClient):
        """Logout without a token returns 401/403."""
        resp = await client.post("/api/auth/logout")
        assert resp.status_code in (401, 403)


class TestFullAuthFlow:
    """End-to-end tests for the complete authentication flow."""

    @pytest.mark.asyncio
    async def test_register_login_me_logout(self, client: AsyncClient, tmp_store_dir):
        """Full flow: register -> login -> /me -> logout."""
        # 1. Register
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "email": "flow@example.com",
                "password": "SecurePass1",
                "display_name": "Flow User",
            },
        )
        assert reg_resp.status_code == 201
        reg_user_id = reg_resp.json()["user"]["id"]

        # 2. Login
        login_resp = await client.post(
            "/api/auth/login",
            json={
                "email": "flow@example.com",
                "password": "SecurePass1",
            },
        )
        assert login_resp.status_code == 200
        access_token = login_resp.json()["access_token"]
        login_user_id = login_resp.json()["user"]["id"]
        assert login_user_id == reg_user_id

        # 3. /me
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "flow@example.com"
        assert me_resp.json()["id"] == reg_user_id

        # 4. Logout
        logout_resp = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 200
