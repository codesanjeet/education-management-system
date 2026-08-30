from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import enum


# ==================================================
# ENUMS
# ==================================================

class PaymentMethodEnum(str, enum.Enum):
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"


class PaymentStatusEnum(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PENDING = "PENDING"


class DiscountTypeEnum(str, enum.Enum):
    FIXED = "FIXED"
    PERCENTAGE = "PERCENTAGE"


class RefundStatusEnum(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class InvoiceStatusEnum(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


# ==================================================
# PAGINATION
# ==================================================

class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================================================
# FEE STRUCTURE SCHEMAS
# ==================================================


# Indian academic year months in order: Apr→Mar
VALID_MONTHS = list(range(1, 13))   # 1–12


MONTH_NAMES = {
    1: "January",  2: "February",  3: "March",
    4: "April",    5: "May",       6: "June",
    7: "July",     8: "August",    9: "September",
    10: "October", 11: "November", 12: "December",
}


class FeeItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=0, decimal_places=2)


class FeeStructureCreate(BaseModel):
    class_code: Optional[str] = None
    apply_to_all: bool = False
    name: str = Field(..., min_length=2, max_length=100)
    academic_year: str = Field(..., min_length=4, max_length=20)
    #  List of month numbers e.g. [4, 7, 10, 3]
    applicable_months: List[int] = Field(..., min_length=1, description="Month numbers 1-12")
    currency: str = Field("INR", max_length=10)
    description: Optional[str] = Field(None, max_length=500)
    items: List[FeeItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_all(self):
        if not self.items:
            raise ValueError("At least one fee item required")
        if not self.apply_to_all and not self.class_code:
            raise ValueError("Either class_code or apply_to_all must be provided")
        if not self.applicable_months:
            raise ValueError("Select at least one month")
        invalid = [m for m in self.applicable_months if m not in VALID_MONTHS]
        if invalid:
            raise ValueError(f"Invalid month numbers: {invalid}")
        # Deduplicate
        self.applicable_months = list(set(self.applicable_months))
        return self


class FeeStructureUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    academic_year: Optional[str] = Field(None, min_length=4, max_length=20)
    applicable_months: Optional[List[int]] = None
    description: Optional[str] = Field(None, max_length=500)
    items: Optional[List[FeeItem]] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_months(self):
        if self.applicable_months is not None:
            if not self.applicable_months:
                raise ValueError("Select at least one month")
            invalid = [m for m in self.applicable_months if m not in VALID_MONTHS]
            if invalid:
                raise ValueError(f"Invalid month numbers: {invalid}")
            self.applicable_months = list(set(self.applicable_months))
        return self


class FeeStructureResponse(BaseModel):
    id: int
    name: str
    academic_year: str
    currency: str
    description: Optional[str]
    applicable_months: List[int]   # e.g. [4, 7, 10, 3]
    structure_json: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# ==================================================
# BILLING SETTINGS SCHEMAS
# ==================================================

class BillingSettingsResponse(BaseModel):
    billing_day: int   # day of month invoices are generated (e.g. 25)
    due_day: int       # day of next month payment is due (e.g. 5)


class BillingSettingsUpdate(BaseModel):
    billing_day: Optional[int] = Field(None, ge=1, le=28)
    due_day: Optional[int] = Field(None, ge=1, le=28)


# ==================================================
# INVOICE SCHEMAS
# ==================================================

class InvoiceItemCreate(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    quantity: int = Field(1, ge=1)
    unit_amount: Decimal = Field(..., ge=0, decimal_places=2)


class InvoiceCreate(BaseModel):
    student_user_id: int
    fee_structure_id: Optional[int] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=1000)
    items: List[InvoiceItemCreate] = Field(..., min_length=1)


class InvoiceItemResponse(BaseModel):
    id: int
    item_name: str
    description: Optional[str]
    quantity: int
    unit_amount: Decimal
    total: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


# Nested student info embedded in invoice
class InvoiceStudentInfo(BaseModel):
    user_id: int
    full_name: str
    email: str
    roll_number: str
    class_code: str
    class_display_name: Optional[str] = None   # e.g. "Class 10 – A"
    contact_num: Optional[str] = None
    profile_image: Optional[dict] = None
    # Guardian / parent info for the invoice PDF
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_contact_num: Optional[str] = None

    model_config = {"from_attributes": True}



class InvoiceResponse(BaseModel):
    invoice_number: str         
    fee_structure_id: Optional[int]  
    issue_date: datetime
    due_date: Optional[datetime]
    subtotal: Decimal
    discount_total: Decimal
    fine_total: Decimal
    paid_total: Decimal
    grand_total: Decimal
    balance_due: Decimal
    status: InvoiceStatusEnum
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    items: List[InvoiceItemResponse] = []
    # Enriched student data
    student: Optional[InvoiceStudentInfo] = None

    model_config = {"from_attributes": True}



class InvoiceListResponse(BaseModel):
    invoice_number: str 
    issue_date: datetime
    due_date: Optional[datetime]
    grand_total: Decimal
    balance_due: Decimal
    status: InvoiceStatusEnum
    # Enriched student data (always included for list)
    student: Optional[InvoiceStudentInfo] = None

    model_config = {"from_attributes": True}


class PaginatedInvoiceResponse(BaseModel):
    items: List[InvoiceListResponse]
    meta: PaginationMeta


# ==================================================
# PAYMENT SCHEMAS
# ==================================================

class PaymentCreate(BaseModel):
    amount_paid: Decimal = Field(..., gt=0, decimal_places=2, description="Must be greater than 0")
    payment_method: PaymentMethodEnum
    transaction_ref: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=500)


class PaymentStudentInfo(BaseModel):
    user_id: int
    full_name: str
    email: str
    roll_number: str
    class_code: str

    model_config = {"from_attributes": True}




class PaymentResponse(BaseModel):
    receipt_number: str          
    invoice_number: Optional[str] = None
    amount_paid: Decimal
    payment_method: PaymentMethodEnum
    transaction_ref: Optional[str]
    payment_status: PaymentStatusEnum
    paid_at: datetime
    notes: Optional[str]
    created_at: datetime
    # Enriched data
    student: Optional[PaymentStudentInfo] = None

    model_config = {"from_attributes": True}


class PaginatedPaymentResponse(BaseModel):
    items: List[PaymentResponse]
    meta: PaginationMeta


# ==================================================
# DISCOUNT SCHEMAS
# ==================================================

class DiscountCreate(BaseModel):
    student_user_id: int
    title: str = Field(..., min_length=2, max_length=100, description="e.g. Scholarship, Sibling Discount")
    reason: Optional[str] = Field(None, max_length=500)
    discount_type: DiscountTypeEnum
    value: Decimal = Field(..., gt=0, decimal_places=2)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_percentage(self):
        if self.discount_type == DiscountTypeEnum.PERCENTAGE and self.value > 100:
            raise ValueError("Percentage discount cannot exceed 100")
        return self

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class DiscountUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=100)
    reason: Optional[str] = Field(None, max_length=500)
    value: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    is_active: Optional[bool] = None
    end_date: Optional[datetime] = None


class DiscountResponse(BaseModel):
    id: int
    student_user_id: int
    title: str
    reason: Optional[str]
    discount_type: DiscountTypeEnum
    value: Decimal
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================================================
# FINE SCHEMAS
# ==================================================

class FineCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=100, description="e.g. Late Payment Fine")
    reason: Optional[str] = Field(None, max_length=500)
    amount: Decimal = Field(..., gt=0, decimal_places=2)


class FineResponse(BaseModel):
    id: int
    title: str
    reason: Optional[str]
    amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================================================
# REFUND SCHEMAS
# ==================================================

class RefundCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    reason: Optional[str] = Field(None, max_length=500)



class RefundResponse(BaseModel):
    amount: Decimal
    reason: Optional[str]
    refund_status: RefundStatusEnum
    refunded_at: datetime

    model_config = {"from_attributes": True}


# ==================================================
# DASHBOARD SCHEMAS
# ==================================================

class ClassCollectionStat(BaseModel):
    class_code: str
    class_or_year_or_name: str
    section: str
    total_invoiced: Decimal
    total_collected: Decimal
    collection_rate: float  # percentage 0–100


class PaymentMethodStat(BaseModel):
    method: PaymentMethodEnum
    total_amount: Decimal
    transaction_count: int
    percentage: float  # share of total collected


class UpcomingDeadline(BaseModel):
    due_date: datetime
    invoice_count: int
    total_balance_due: Decimal
    days_until_due: int


class FeeDashboardResponse(BaseModel):
    # ── Top stat cards ──────────────────────────────
    total_collected: Decimal
    pending_amount: Decimal
    overdue_amount: Decimal
    total_students_with_invoices: int
    fully_paid_students: int
    collection_rate: float           # percentage 0–100
    invoices_this_month: int
    discounts_applied_this_month: int

    # ── Class-wise collection ────────────────────────
    class_collection: List[ClassCollectionStat]

    # ── Payment method breakdown ─────────────────────
    payment_methods: List[PaymentMethodStat]

    # ── Upcoming / overdue deadlines ─────────────────
    upcoming_deadlines: List[UpcomingDeadline]

    model_config = {"from_attributes": True}