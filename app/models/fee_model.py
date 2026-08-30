from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Numeric,
    Text,
    Enum,

)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base
import enum


class InvoiceStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"

# ==================================================
# FEE STRUCTURE
# ==================================================

class FeeStructureDB(Base):
    __tablename__ = "fee_structures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)
    academic_year = Column(String(20), nullable=False)
    currency = Column(String(10), default="INR")
    description = Column(Text, nullable=True)
# remember me
    applicable_months = Column(JSONB, nullable=False, default=list)

    structure_json = Column(JSONB, nullable=False, default=dict)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    invoices = relationship("InvoiceDB", back_populates="fee_structure", passive_deletes=True)
# ==================================================
# INVOICES
# ==================================================

class InvoiceDB(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)

    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fee_structure_id = Column(Integer, ForeignKey("fee_structures.id", ondelete="SET NULL"), nullable=True)

    invoice_number = Column(String(50), unique=True, nullable=False, index=True)

    issue_date = Column(DateTime, default=lambda: datetime.utcnow())
    due_date = Column(DateTime, nullable=True)

    subtotal = Column(Numeric(12, 2), default=0)
    discount_total = Column(Numeric(12, 2), default=0)
    fine_total = Column(Numeric(12, 2), default=0)
    paid_total = Column(Numeric(12, 2), default=0)
    grand_total = Column(Numeric(12, 2), default=0)
    balance_due = Column(Numeric(12, 2), default=0)

    status = Column(
        Enum(InvoiceStatus, name="invoice_status"),
        default=InvoiceStatus.UNPAID,
        nullable=False
    )
    # UNPAID / PARTIAL / PAID / OVERDUE / CANCELLED

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    fee_structure = relationship("FeeStructureDB", back_populates="invoices")
    items = relationship("InvoiceItemDB", back_populates="invoice", passive_deletes=True)
    payments = relationship("PaymentDB", back_populates="invoice", passive_deletes=True)
    fines = relationship("FineDB", back_populates="invoice", passive_deletes=True)


# ==================================================
# INVOICE ITEMS
# ==================================================

class InvoiceItemDB(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)

    item_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    quantity = Column(Integer, default=1)
    unit_amount = Column(Numeric(12, 2), default=0)
    total = Column(Numeric(12, 2), default=0)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    invoice = relationship("InvoiceDB", back_populates="items")


# ==================================================
# PAYMENTS
# ==================================================

class PaymentDB(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)

    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    receipt_number = Column(String(50), unique=True, nullable=False, index=True)

    amount_paid = Column(Numeric(12, 2), nullable=False)

    payment_method = Column(String(30), nullable=False)
    # CASH / UPI / CARD / BANK_TRANSFER / CHEQUE

    transaction_ref = Column(String(255), nullable=True)

    payment_status = Column(String(30), default="SUCCESS")
    # SUCCESS / FAILED / REFUNDED / PENDING

    paid_at = Column(DateTime, default=lambda: datetime.utcnow())
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    invoice = relationship("InvoiceDB", back_populates="payments")
    refunds = relationship("RefundDB", back_populates="payment", passive_deletes=True)


# ==================================================
# DISCOUNTS
# ==================================================

class DiscountDB(Base):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(100), nullable=False)  # Scholarship
    reason = Column(Text, nullable=True)

    discount_type = Column(String(20), default="FIXED")
    # FIXED / PERCENTAGE

    value = Column(Numeric(12, 2), nullable=False)

    is_active = Column(Boolean, default=True)

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ==================================================
# FINES
# ==================================================

class FineDB(Base):
    __tablename__ = "fines"

    id = Column(Integer, primary_key=True, autoincrement=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(100), nullable=False)
    reason = Column(Text, nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    invoice = relationship("InvoiceDB", back_populates="fines")


# ==================================================
# REFUNDS
# ==================================================

class RefundDB(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, autoincrement=True)

    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=True)

    refund_status = Column(String(30), default="SUCCESS")
    refunded_at = Column(DateTime, default=lambda: datetime.utcnow())
    payment = relationship("PaymentDB", back_populates="refunds")