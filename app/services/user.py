from sqlalchemy.ext.asyncio import AsyncSession
from ..models.user_model import UserDB
from ..models.super_admin_model import SuperAdminDB
from ..crud.super_admin_crud import get_super_admin_by_id

async def get_valid_user(
    db: AsyncSession,
    identifier: str,
    tenant_id: int
) -> UserDB | None:
    # to overcome circular import
    from ..crud.user_fun import get_user_by_username_or_email

    user = await get_user_by_username_or_email(db, identifier, tenant_id)

    if not user:
        return None

    if user.deleted_date is not None:
        return None
    
    if not user.is_active:     
        return None

    if user.is_block:
        return None

    return user


# super admin
async def get_valid_super_admin_user(
    db: AsyncSession,
    super_admin_id: int 
) -> SuperAdminDB | None:
    # to overcome circular import

    user = await get_super_admin_by_id(db, super_admin_id)

    if not user:
        return None


    if user.is_block:
        return None

    return user
