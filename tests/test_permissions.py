"""
Tests for the authorization helpers in app/deps.py.

These call the dependency functions directly with a hand-built
CurrentUserResponse instead of going through get_current_user (which needs
a DB session to look up the user). require_permission() etc. take
current_user as a plain argument with a Depends() default, so calling them
outside of FastAPI's injection is a legitimate way to exercise the actual
authorization logic in isolation.
"""
import pytest
from fastapi import HTTPException

from app.deps import (
    has_permission,
    require_any_permission,
    require_permission,
    require_permission_or_owner,
)
from conftest import make_current_user


@pytest.mark.asyncio
async def test_require_permission_allows_when_present():
    checker = require_permission("student:delete")
    user = make_current_user(permissions=["student:delete"])
    result = await checker(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_permission_blocks_when_missing():
    checker = require_permission("student:delete")
    user = make_current_user(permissions=["student:view"])
    with pytest.raises(HTTPException) as exc_info:
        await checker(current_user=user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_checks_all_of_multiple():
    checker = require_permission("student:view", "student:update")
    user = make_current_user(permissions=["student:view"])  # missing update
    with pytest.raises(HTTPException) as exc_info:
        await checker(current_user=user)
    assert "student:update" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_any_permission_allows_partial_match():
    checker = require_any_permission("staff:create", "staff:update")
    user = make_current_user(permissions=["staff:update"])
    result = await checker(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_any_permission_blocks_when_none_match():
    checker = require_any_permission("staff:create", "staff:update")
    user = make_current_user(permissions=["staff:view"])
    with pytest.raises(HTTPException) as exc_info:
        await checker(current_user=user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_or_owner_allows_owner_without_permission():
    checker = require_permission_or_owner("student:update")
    user = make_current_user(id=42, permissions=[])
    result = await checker(user_id=42, current_user=user)
    assert result["is_owner"] is True
    assert result["has_permission"] is False


@pytest.mark.asyncio
async def test_require_permission_or_owner_allows_permission_without_owner():
    checker = require_permission_or_owner("student:update")
    user = make_current_user(id=1, permissions=["student:update"])
    result = await checker(user_id=42, current_user=user)
    assert result["is_owner"] is False
    assert result["has_permission"] is True


@pytest.mark.asyncio
async def test_require_permission_or_owner_blocks_stranger():
    checker = require_permission_or_owner("student:update")
    user = make_current_user(id=1, permissions=[])
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_id=42, current_user=user)
    assert exc_info.value.status_code == 403


def test_has_permission_handles_missing_user():
    assert has_permission(None, "student:view") is False


def test_has_permission_true_and_false():
    user = make_current_user(permissions=["student:view"])
    assert has_permission(user, "student:view") is True
    assert has_permission(user, "student:delete") is False
