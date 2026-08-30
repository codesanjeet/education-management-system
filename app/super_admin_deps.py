from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_token
from app.core.database import get_db
from app.schemas.super_admin_schema import CurrentSuperAdminResponse
from app.services.user import get_valid_super_admin_user
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_super_admin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)      
) -> CurrentSuperAdminResponse:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    if payload.get("type") != "super_admin":
        raise credentials_exception

    super_admin_id: int = payload.get("super_admin_id")
    email: str = payload.get("sub")
    role: str = payload.get("role")

    if not all([super_admin_id, email, role]):
        raise credentials_exception

    user = await get_valid_super_admin_user(db, super_admin_id)
    if user is None or user.is_block:
        raise credentials_exception

    return CurrentSuperAdminResponse(
        id=super_admin_id,
        user_name=user.user_name,
        email=email,
        role=role,
        permissions=[],
        is_block=user.is_block,
        profile_image=user.profile_image,
        name=user.name,
    )