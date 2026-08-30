"""
Tenant isolation is enforced primarily through the JWT: every access token
carries a tenant_id, and app/deps.get_current_user refuses to authenticate
a request whose token doesn't have one. These tests exercise that guarantee
at the token layer, without needing a seeded multi-tenant database.
"""
import pytest
from fastapi import HTTPException
import jwt as pyjwt

from app.core.security import create_access_token, decode_token
from app.core.config import settings
from app.deps import get_current_user


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_without_tenant_id():
    # Same payload shape as a real login, minus tenant_id.
    token = create_access_token({"sub": "user@example.com", "user_id": 1, "role": "teacher"})

    with pytest.raises(HTTPException) as exc_info:
        # db is never touched before the tenant_id check runs, so None is fine here.
        await get_current_user(token=token, db=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_token_missing_role():
    token = create_access_token({"sub": "user@example.com", "user_id": 1, "tenant_id": "tenant-1"})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=None)
    assert exc_info.value.status_code == 401


def test_decode_token_preserves_tenant_id():
    token = create_access_token(
        {"sub": "user@example.com", "user_id": 1, "tenant_id": "tenant-42", "role": "admin"}
    )
    payload = decode_token(token)
    assert payload["tenant_id"] == "tenant-42"


def test_decode_token_rejects_token_signed_with_different_key():
    # Simulates a token forged/signed without knowledge of the real
    # SECRET_KEY -- e.g. an attacker trying to mint a token for another
    # tenant. decode_token must not accept it.
    forged = pyjwt.encode(
        {"sub": "attacker@example.com", "user_id": 999, "tenant_id": "some-other-tenant", "role": "admin"},
        "a-completely-different-secret-that-is-long-enough",
        algorithm=settings.ALGORITHM,
    )
    assert decode_token(forged) is None


def test_decode_token_rejects_expired_token():
    from datetime import timedelta

    token = create_access_token(
        {"sub": "user@example.com", "user_id": 1, "tenant_id": "tenant-1", "role": "teacher"},
        expires_delta=timedelta(seconds=-1),
    )
    assert decode_token(token) is None
