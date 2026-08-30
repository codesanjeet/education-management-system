"""
The app maps ~25 custom exception types to specific HTTP responses via
app.add_exception_handler(...) in app/main.py (see app/core/exception_handlers.py).
None of that mapping was covered anywhere, and it's easy to break silently
(wrong status code, wrong exception class, handler never registered) since
it's rarely hit in normal manual testing. These call the handlers directly
with a bare exception instance -- `request` is only used for logging, so
None is fine here.
"""
import pytest

from app.core.exception_handlers import (
    class_capacity_handler,
    database_error_handler,
    general_exception_handler,
    insufficient_permission_handler,
    not_found_handler,
    rate_limit_exceeded_handler,
    user_already_exists_handler,
    user_not_found_handler,
    value_error_handler,
)
from app.core.exceptions import (
    ClassCapacityExceededError,
    DatabaseError,
    InsufficientPermissionError,
    NotFoundError,
    RateLimitExceededError,
    UserAlreadyExistsError,
    UserNotFoundException,
)


@pytest.mark.asyncio
async def test_user_not_found_maps_to_404():
    response = await user_not_found_handler(None, UserNotFoundException("gone"))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_already_exists_maps_to_409():
    response = await user_already_exists_handler(None, UserAlreadyExistsError("dup"))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_class_capacity_exceeded_maps_to_400_and_preserves_message():
    response = await class_capacity_handler(None, ClassCapacityExceededError("Class 10-A is full"))
    assert response.status_code == 400
    assert b"Class 10-A is full" in response.body


@pytest.mark.asyncio
async def test_generic_database_error_maps_to_400_without_leaking_details():
    # Should NOT echo the raw DB error message back to the client.
    response = await database_error_handler(None, DatabaseError("connection to server lost"))
    assert response.status_code == 400
    assert b"connection to server lost" not in response.body


@pytest.mark.asyncio
async def test_value_error_maps_to_400_and_preserves_message():
    response = await value_error_handler(None, ValueError("Invalid month numbers: [13]"))
    assert response.status_code == 400
    assert b"Invalid month numbers" in response.body


@pytest.mark.asyncio
async def test_unhandled_exception_maps_to_500_without_leaking_details():
    response = await general_exception_handler(None, Exception("secret internal detail"))
    assert response.status_code == 500
    assert b"secret internal detail" not in response.body


@pytest.mark.asyncio
async def test_insufficient_permission_maps_to_403():
    response = await insufficient_permission_handler(None, InsufficientPermissionError())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rate_limit_exceeded_maps_to_429():
    response = await rate_limit_exceeded_handler(None, RateLimitExceededError())
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_not_found_error_maps_to_404():
    response = await not_found_handler(None, NotFoundError())
    assert response.status_code == 404
