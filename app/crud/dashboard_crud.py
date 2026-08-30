from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func,case
from app.models.user_model import UserDB
from app.models.institution_model import InstitutionDB,ActivityLogDB
from ..models.user_model import UserDB
from ..models.fee_model import InvoiceDB,InvoiceStatus,PaymentDB
from ..models.user_model import UserRoleEnum
from ..models.classes_model import ClassDB
from ..models.role_specific.student_model import StudentDB
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, func
from app.crud.class_crud import get_today_staff_schedule
from app.crud.remarks_crud import get_all_remarks
from app.crud.attendance_crud import get_days_institution_attendance_agg
async def get_recent_activity_for_dashboard(
    tenant_id: str,
    db: AsyncSession
):
    result = await db.execute(
        select(ActivityLogDB)
        .where(ActivityLogDB.tenant_id == tenant_id)
        .order_by(ActivityLogDB.created_at.desc())
        .limit(10)
    )

    return result.scalars().all()


async def get_dashboard_data(db: AsyncSession, tenant_id: str,user_id):
# stat
    result = await db.execute(
        select(
            func.count(UserDB.id)
            .filter(UserDB.role == UserRoleEnum.STUDENT)
            .label("students"),

            func.count(UserDB.id)
            .filter(
                UserDB.role.in_([
                    UserRoleEnum.TEACHER.value,
                    UserRoleEnum.OTHER_STAFF.value,
                    UserRoleEnum.PRINCIPAL.value,
                    UserRoleEnum.ADMIN.value
                ])
            )
            .label("staffs")
        ).where(
            UserDB.tenant_id == tenant_id,
            UserDB.deleted_date.is_(None)
        )
    )
    row = result.one()

    class_count = await db.execute(
        select(func.count(ClassDB.id))
        .join(InstitutionDB)
        .where(
            InstitutionDB.tenant_id == tenant_id,
            ClassDB.deleted_date.is_(None)
        )
    )
# class distribution
    class_ = await db.execute(
        select(
            ClassDB.class_code,
            ClassDB.class_or_year_or_name,
            func.count(StudentDB.id).label("student_count")
        )
        .join(StudentDB, StudentDB.class_code == ClassDB.class_code, isouter=True)
        .join(InstitutionDB)
        .where(
            InstitutionDB.tenant_id == tenant_id,
            ClassDB.deleted_date.is_(None)
        )
        .group_by(
            ClassDB.id,
            ClassDB.class_code,
            ClassDB.class_or_year_or_name
        )
    )

    class_rows = class_.all()

    # today class schedule
    today_classes =await get_today_staff_schedule(db=db, user_id= user_id, tenant_id=tenant_id)

    # my given remarks
    my_remarks = await get_all_remarks(current_user_id = user_id, db=db, tenant_id=tenant_id)

    #day wise inst attendance 
    attendance = await get_days_institution_attendance_agg(tenant_id=tenant_id, db= db)

    # finanacial 
    financial_q = await db.execute(
        select(
            func.sum(InvoiceDB.paid_total).label("total_collected"),
            func.sum(
                case(
                    (
                        InvoiceDB.status.in_([
                            InvoiceStatus.UNPAID,
                            InvoiceStatus.PARTIAL,
                            InvoiceStatus.OVERDUE,
                        ]),
                        InvoiceDB.balance_due,
                    ),
                    else_=0,
                )
            ).label("pending_amount"),
        )
    )
    financial_data = financial_q.one()
    six_months_ago = datetime.utcnow() - relativedelta(months=6)

    month_trunc = func.date_trunc("month", PaymentDB.created_at)

    monthly_q = await db.execute(
        select(
            month_trunc.label("month"),
            func.sum(PaymentDB.amount_paid).label("total_collected"),
        )
        .where(PaymentDB.created_at >= six_months_ago)
        .group_by(month_trunc)
        .order_by(month_trunc)
    )
    monthly_data = monthly_q.all()

    return {
        "stat":{
        "total_students": row.students,
        "total_staff": row.staffs,
        "total_classes": class_count.scalar_one()
        },
        "class_distribution":[
        {
            "class_code": r.class_code,
            "class_name": r.class_or_year_or_name,
            "student_count": r.student_count
        }
        for r in class_rows
    ],
        "today_class_schedule":
           today_classes
        ,
        "my_given_remarks": my_remarks,
        "weekly_inst_attendance": attendance,
        "pending_amount": financial_data.pending_amount,
        "total_collected": financial_data.total_collected,
        "monthly_collection":[
            {
                "month": r.month.strftime("%Y-%m"),
                "total_collected": r.total_collected
            }
            for r in monthly_data
        ]

    }

async def create_recent_activity_log(db: AsyncSession, tenant_id: str, user_id: int, action_type: str, message: str):
    new_log = ActivityLogDB(
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=action_type,
        message=message,
        institution_id = await db.scalar(select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id))
    )
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)
    return new_log