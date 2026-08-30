import pytest

from app.routers.auth_router import validate_password


# ─────────────────────────────────────────────────────────────────────────
# /api/auth/login
# ─────────────────────────────────────────────────────────────────────────
# Login uses OAuth2PasswordRequestForm + a separate tenant_id form field
# (see auth_router.login), so it's submitted as form data, not JSON.

@pytest.mark.asyncio
async def test_login_missing_fields_returns_422(client):
    response = await client.post("/api/auth/login", data={"username": "test@example.com"})
    assert response.status_code == 422
    missing = {err["loc"][-1] for err in response.json()["detail"]}
    assert "password" in missing
    assert "tenant_id" in missing


@pytest.mark.asyncio
async def test_login_rejects_json_body(client):
    # Sending JSON instead of form-encoded data means none of the required
    # form fields are present, so this should fail validation the same way.
    response = await client.post(
        "/api/auth/login",
        json={"username": "test@example.com", "password": "x", "tenant_id": "t1"},
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# /api/auth/check-email
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_email_missing_identifier_returns_422(client):
    response = await client.post("/api/auth/check-email", json={})
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# Protected endpoints
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client):
    response = await client.get("/api/institutions/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_malformed_token(client):
    response = await client.get(
        "/api/institutions/users/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_wrong_scheme(client):
    # Only "Bearer <token>" is accepted.
    response = await client.get(
        "/api/institutions/users/me",
        headers={"Authorization": "Token whatever"},
    )
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# Password policy (validate_password in auth_router.py)
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "password, should_pass",
    [
        ("Abcdef1", True),        # upper + lower + digit, 6+ chars
        ("abcdef1", False),       # no uppercase
        ("ABCDEF1", False),       # no lowercase
        ("Abcdefg", False),       # no digit
        ("Ab1", False),           # too short
    ],
)
def test_password_policy(password, should_pass):
    assert bool(validate_password(password)) is should_pass
