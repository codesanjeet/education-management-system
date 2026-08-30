import pytest
from pydantic import ValidationError

from app.schemas.institution_schema import ContactSubmissionCreate, InstitutionCreate, InstitutionType


# ─────────────────────────────────────────────────────────────────────────
# InstitutionCreate validation (app/schemas/institution_schema.py)
# ─────────────────────────────────────────────────────────────────────────

VALID_INSTITUTION = dict(
    institute_name="Sunrise Public School",
    address="123 MG Road, Near City Center",
    phone="9876543210",
    city="Patna",
    state="Bihar",
    pincode="800001",
    country="India",
    phone_country_code="91",
    email="admin@sunrise.example.com",
    institution_type=InstitutionType.SCHOOL,
)


def test_institution_create_accepts_valid_data():
    institution = InstitutionCreate(**VALID_INSTITUTION)
    assert institution.institute_name == "Sunrise Public School"


def test_institution_create_rejects_short_name():
    with pytest.raises(ValidationError):
        InstitutionCreate(**{**VALID_INSTITUTION, "institute_name": "AB"})


def test_institution_create_rejects_invalid_email():
    with pytest.raises(ValidationError):
        InstitutionCreate(**{**VALID_INSTITUTION, "email": "not-an-email"})


def test_institution_create_rejects_unknown_institution_type():
    with pytest.raises(ValidationError):
        InstitutionCreate(**{**VALID_INSTITUTION, "institution_type": "university"})


# ─────────────────────────────────────────────────────────────────────────
# ContactSubmissionCreate -- basic XSS guard on free-text fields
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "payload",
    [
        {"name": "<script>alert(1)</script>", "institute": "X", "email": "a@b.com", "message": "Hello there"},
        {"name": "Asha", "institute": "<iframe src=x>", "email": "a@b.com", "message": "Hello there"},
        {"name": "Asha", "institute": "X", "email": "a@b.com", "message": "javascript:alert(1)"},
    ],
)
def test_contact_submission_rejects_script_content(payload):
    with pytest.raises(ValidationError):
        ContactSubmissionCreate(**payload)


def test_contact_submission_accepts_clean_data():
    submission = ContactSubmissionCreate(
        name="Asha Kumar",
        institute="Sunrise Public School",
        email="asha@example.com",
        message="I'd like to know more about your fee structure.",
    )
    assert submission.name == "Asha Kumar"


# ─────────────────────────────────────────────────────────────────────────
# Endpoint authorization
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_institution_requires_form_fields(client):
    # Registration is public (no auth), but still validates the payload.
    response = await client.post("/api/institutions", data={"institute_name": "AB"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_logo_requires_auth(client):
    response = await client.patch("/api/logo")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_all_institutions_requires_super_admin_auth(client):
    response = await client.get("/api/super-admin/institutions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_contacts_requires_super_admin_auth(client):
    response = await client.get("/api/super-admin/contacts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_contact_form_rejects_script_content_over_http(client):
    response = await client.post(
        "/api/contact",
        json={
            "name": "<script>alert(1)</script>",
            "institute": "X",
            "email": "a@b.com",
            "message": "Hello there",
        },
    )
    assert response.status_code == 422
