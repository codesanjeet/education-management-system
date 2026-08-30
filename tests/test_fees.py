from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.crud.fee_crud import _recalculate_invoice
from app.models.fee_model import FineDB, InvoiceDB, InvoiceItemDB, InvoiceStatus, PaymentDB
from app.schemas.fee_schema import FeeItem, FeeStructureCreate, PaymentCreate


# ─────────────────────────────────────────────────────────────────────────
# _recalculate_invoice (app/crud/fee_crud.py) -- the core billing math.
# Builds InvoiceDB instances in memory; no DB session needed since we
# assign the relationship collections (items/fines/payments) directly.
# ─────────────────────────────────────────────────────────────────────────

def _invoice(discount_total="0"):
    invoice = InvoiceDB(discount_total=Decimal(discount_total))
    invoice.items = []
    invoice.fines = []
    invoice.payments = []
    return invoice


def test_recalculate_invoice_unpaid():
    invoice = _invoice()
    invoice.items = [InvoiceItemDB(total=Decimal("1000"))]

    _recalculate_invoice(invoice)

    assert invoice.subtotal == Decimal("1000")
    assert invoice.grand_total == Decimal("1000")
    assert invoice.balance_due == Decimal("1000")
    assert invoice.status == InvoiceStatus.UNPAID


def test_recalculate_invoice_partial_payment():
    invoice = _invoice(discount_total="100")
    invoice.items = [InvoiceItemDB(total=Decimal("1000"))]
    invoice.fines = [FineDB(amount=Decimal("50"))]
    invoice.payments = [PaymentDB(amount_paid=Decimal("500"), payment_status="SUCCESS")]

    _recalculate_invoice(invoice)

    # grand_total = subtotal - discount + fines = 1000 - 100 + 50 = 950
    assert invoice.grand_total == Decimal("950")
    assert invoice.balance_due == Decimal("450")
    assert invoice.status == InvoiceStatus.PARTIAL


def test_recalculate_invoice_fully_paid():
    invoice = _invoice()
    invoice.items = [InvoiceItemDB(total=Decimal("500"))]
    invoice.payments = [PaymentDB(amount_paid=Decimal("500"), payment_status="SUCCESS")]

    _recalculate_invoice(invoice)

    assert invoice.balance_due == Decimal("0")
    assert invoice.status == InvoiceStatus.PAID


def test_recalculate_invoice_ignores_failed_payments():
    invoice = _invoice()
    invoice.items = [InvoiceItemDB(total=Decimal("500"))]
    invoice.payments = [
        PaymentDB(amount_paid=Decimal("500"), payment_status="FAILED"),
    ]

    _recalculate_invoice(invoice)

    # A failed payment shouldn't count toward paid_total.
    assert invoice.paid_total == Decimal("0")
    assert invoice.balance_due == Decimal("500")
    assert invoice.status == InvoiceStatus.UNPAID


def test_recalculate_invoice_overpayment_still_counts_as_paid():
    invoice = _invoice()
    invoice.items = [InvoiceItemDB(total=Decimal("500"))]
    invoice.payments = [PaymentDB(amount_paid=Decimal("600"), payment_status="SUCCESS")]

    _recalculate_invoice(invoice)

    assert invoice.balance_due < 0
    assert invoice.status == InvoiceStatus.PAID


# ─────────────────────────────────────────────────────────────────────────
# FeeStructureCreate validation (app/schemas/fee_schema.py)
# ─────────────────────────────────────────────────────────────────────────

def _fee_structure(**overrides):
    base = dict(
        name="Term Fee",
        academic_year="2025-26",
        apply_to_all=True,
        applicable_months=[4, 5],
        items=[FeeItem(name="Tuition", amount=Decimal("1000"))],
    )
    base.update(overrides)
    return FeeStructureCreate(**base)


def test_fee_structure_requires_class_code_or_apply_to_all():
    with pytest.raises(ValidationError, match="class_code or apply_to_all"):
        _fee_structure(apply_to_all=False, class_code=None)


def test_fee_structure_rejects_invalid_month_numbers():
    with pytest.raises(ValidationError, match="Invalid month numbers"):
        _fee_structure(applicable_months=[4, 13])


def test_fee_structure_deduplicates_months():
    fs = _fee_structure(applicable_months=[4, 4, 5, 5, 6])
    assert sorted(fs.applicable_months) == [4, 5, 6]


def test_fee_structure_requires_at_least_one_item():
    with pytest.raises(ValidationError):
        _fee_structure(items=[])


def test_fee_item_rejects_negative_amount():
    with pytest.raises(ValidationError):
        FeeItem(name="Tuition", amount=Decimal("-1"))


# ─────────────────────────────────────────────────────────────────────────
# PaymentCreate validation
# ─────────────────────────────────────────────────────────────────────────

def test_payment_create_rejects_zero_amount():
    with pytest.raises(ValidationError):
        PaymentCreate(amount_paid=Decimal("0"), payment_method="CASH")


def test_payment_create_rejects_negative_amount():
    with pytest.raises(ValidationError):
        PaymentCreate(amount_paid=Decimal("-50"), payment_method="CASH")


def test_payment_create_accepts_valid_amount():
    payment = PaymentCreate(amount_paid=Decimal("500.00"), payment_method="UPI")
    assert payment.amount_paid == Decimal("500.00")


# ─────────────────────────────────────────────────────────────────────────
# Endpoint authorization
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_fee_structure_requires_auth(client):
    response = await client.post("/api/institutions/fee-structures", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_billing_settings_requires_auth(client):
    response = await client.get("/api/institutions/billing-settings")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_billing_settings_requires_permission(client):
    response = await client.patch("/api/institutions/billing-settings", json={})
    assert response.status_code == 401
