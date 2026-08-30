"""
Shared pytest fixtures.

The app's Settings() (app/core/config.py) requires several env vars with no
defaults (SECRET_KEY, GOOGLE_CLIENT_ID, R2_*, DATABASE_URL, ...), and
app/core/storage.py separately reads R2_PUBLIC_BASE straight from os.environ
(not from Settings). None of that is needed to run these tests -- nothing
here talks to Postgres or R2 -- but the app module has to *import*
successfully first, so we fill in harmless placeholders for anything the
developer hasn't already set in their own environment/.env.
"""
import os

_TEST_DEFAULTS = {
    "SECRET_KEY": "test-secret-key-do-not-use-in-production-min-32-chars",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "OPENAI_API_KEY": "test-openai-key",
    "R2_ACCESS_KEY": "test-r2-access-key",
    "R2_SECRET_KEY": "test-r2-secret-key",
    "R2_ENDPOINT": "https://test.r2.cloudflarestorage.com",
    "R2_PUBLIC_BASE_URL": "https://test-public.example.com",
    # storage.py reads this exact name directly via os.getenv, separate
    # from R2_PUBLIC_BASE_URL above -- both are required for `app.main`
    # to import without raising.
    "R2_PUBLIC_BASE": "https://test-public.example.com",
    "R2_PRIVATE_BUCKET_NAME": "test-private-bucket",
    "R2_PUBLIC_BUCKET_NAME": "test-public-bucket",
    "RESEND_API_KEY": "test-resend-key",
    "EMAIL_FROM_ADDRESS": "test@example.com",
    "NOTIFICATION_EMAIL_TOKEN_SECRET": "test-notification-secret",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_db",
    "BACKEND_BASE_URL": "http://localhost:8000",
    "FRONTEND_BASE_URL": "http://localhost:3000",
}

for key, value in _TEST_DEFAULTS.items():
    os.environ.setdefault(key, value)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.user_schema import CurrentUserResponse


@pytest_asyncio.fixture
async def client():
    """
    Unauthenticated async client wired directly to the ASGI app (no live
    server, no network). Good for anything that doesn't need a real DB:
    validation errors, auth-required checks, public endpoints.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_current_user(
    id: int = 1,
    email: str = "user@example.com",
    role: str = "teacher",
    permissions: list[str] | None = None,
    tenant_id: str = "tenant-1",
) -> CurrentUserResponse:
    """
    Build a CurrentUserResponse without touching the DB. Useful for testing
    authorization logic (app/deps.py) directly, since those dependency
    functions take `current_user` as a normal argument and don't require
    going through the HTTP/JWT layer to be exercised.
    """
    return CurrentUserResponse(
        **{
            "id": id,
            "user_name": email.split("@")[0],
            "email": email,
            "role": role,
            "permissions": permissions or [],
            "first_name": "Test",
            "last_name": "User",
            "tenant_id": tenant_id,
            "is_block": False,
            "deleted_date": None,
            "is_profile_complete": True,
            "profile_image": None,
        }
    )
