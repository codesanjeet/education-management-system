import pytest
from pydantic import ValidationError

from app.schemas.student_schema import StudentCreate

VALID_STUDENT = dict(
    roll_number="R-101",
    guardian_contact_num="9876543210",
    first_name="Asha",
    last_name="Kumar",
    email="Asha@Example.com",
    role="student",
    contact_num="9123456780",
    city="Patna",
    state="Bihar",
)


# ─────────────────────────────────────────────────────────────────────────
# StudentCreate validation (app/schemas/student_schema.py)
# ─────────────────────────────────────────────────────────────────────────

def test_student_create_normalizes_email_and_contact():
    student = StudentCreate(**VALID_STUDENT)
    assert student.email == "asha@example.com"
    assert student.contact_num == "9123456780"


@pytest.mark.parametrize("contact_num", ["98765", "12345678901234567"])
def test_student_create_rejects_bad_contact_length(contact_num):
    with pytest.raises(ValidationError):
        StudentCreate(**{**VALID_STUDENT, "contact_num": contact_num})


def test_student_create_strips_non_digits_before_checking_contact_length():
    # 10 actual digits once separators are stripped -> valid.
    student = StudentCreate(**{**VALID_STUDENT, "contact_num": "91-234-56780"})
    assert student.contact_num == "9123456780"


def test_student_create_rejects_digits_in_name():
    with pytest.raises(ValidationError):
        StudentCreate(**{**VALID_STUDENT, "first_name": "Asha2"})


def test_student_create_rejects_bad_roll_number():
    with pytest.raises(ValidationError):
        StudentCreate(**{**VALID_STUDENT, "roll_number": "R 101!"})


def test_student_create_rejects_bad_pincode():
    with pytest.raises(ValidationError):
        StudentCreate(**{**VALID_STUDENT, "pincode": "abcd"})


def test_student_create_allows_missing_optional_pincode():
    student = StudentCreate(**{k: v for k, v in VALID_STUDENT.items()})
    assert student.pincode is None


# ─────────────────────────────────────────────────────────────────────────
# Endpoint authorization -- creating/reading/modifying students all require
# an authenticated request with the right permission.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_student_requires_auth(client):
    response = await client.post(
        "/api/institutions/students",
        params={"class_code": "C1"},
        json=VALID_STUDENT,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_student_requires_auth(client):
    response = await client.patch("/api/institutions/students/1", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_student_requires_auth(client):
    response = await client.delete("/api/institutions/students/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_students_by_class_requires_auth(client):
    response = await client.get("/api/institutions/students/classes/C1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_single_student_requires_auth(client):
    response = await client.get("/api/institutions/students/1")
    assert response.status_code == 401
