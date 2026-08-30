from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.institution_model import InstitutionDB
from fastapi import HTTPException
from sqlalchemy.future import select
from ..schemas.setting_schema import SecuritySettingResponse,SecuritySettingUpdate


# BRANDING SETTING
# DONE IN INSTITUTION CRUD




# SECURITY SETTING
async def get_security_setting(
    db: AsyncSession,
    tenant_id: str
):
    stmt = select(InstitutionDB).where(
        InstitutionDB.tenant_id == tenant_id
    )

    result = await db.execute(stmt)
    institution = result.scalar_one_or_none()

    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found")


    return SecuritySettingResponse(
        session_timeout=institution.session_timeout
    )


async def update_security_setting(
    db: AsyncSession,
    tenant_id: str,
    payload: SecuritySettingUpdate
):

    stmt = select(InstitutionDB).where(
        InstitutionDB.tenant_id == tenant_id
    )

    result = await db.execute(stmt)
    institution = result.scalar_one_or_none()

    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found")

    institution.session_timeout = payload.session_timeout

    await db.commit()

    return SecuritySettingUpdate(
        session_timeout=institution.session_timeout
    )