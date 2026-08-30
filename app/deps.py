# app/deps.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_token
from app.core.database import get_db
from app.schemas.user_schema import CurrentUserResponse
from app.crud.permission_crud import get_user_permissions
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> CurrentUserResponse:
    """
    Decode token and validate user status
    
    WHY DB QUERY?
    - Check is_active, is_block, deleted_date (can change anytime)
    
    WHY NOT QUERY PERMISSIONS?
    - Already in token, no need for extra query
    """
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Decode token
    payload = decode_token(token)
    
    if payload is None:
        raise credentials_exception
    
    # 2. Extract data from token
    user_id: int = payload.get("user_id")
    email: str = payload.get("sub")
    tenant_id: str = payload.get("tenant_id")
    role: str = payload.get("role")
    permissions: list = payload.get("permissions", [])
    
    if not all([user_id, email, tenant_id, role]):
        raise credentials_exception
    
    # 3. Validate user status (MUST query DB for real-time status)
    from app.services.user import get_valid_user
    
    user = await get_valid_user(db, identifier=email, tenant_id=tenant_id)
    

    if user is None:
        raise credentials_exception
    

    perm = await get_user_permissions(db, user.id)

    permission_names = [p.name for p in perm.permissions] 
    
    # 4. Return user with permissions from token
    return CurrentUserResponse(
        id=user_id,
        user_name=user.user_name,
        email=email,
        role=role,
        permissions=permission_names,  
        tenant_id=tenant_id,
        is_block=user.is_block,
        deleted_date=user.deleted_date,
        is_profile_complete=user.is_profile_complete,
        profile_image=user.profile_image,
        first_name=user.first_name,
        last_name=user.last_name
        
   
    )



def require_permission(*required_permissions: str):

    async def permission_checker(
        current_user: CurrentUserResponse = Depends(get_current_user)
    ):
        user_permissions = getattr(current_user, "permissions", [])

        for permission in required_permissions:
            if permission not in user_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permission: {permission}"
                )

        return current_user

    return permission_checker



def has_permission(user, permission: str) -> bool:
    if not user:
        return False
    user_permissions = getattr(user, 'permissions', {})
    return permission in user_permissions


def require_permission_or_owner(permission: str):
    async def checker(
        user_id: int,
        current_user: CurrentUserResponse = Depends(get_current_user)
    ):
        is_owner = current_user.id == user_id
        user_has_perm = has_permission(current_user, permission)

        if not is_owner and not user_has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return {
            "is_owner": is_owner,
            "has_permission": user_has_perm,
            "current_user": current_user
        }

    return checker


def require_any_permission(*required_permissions: str):

    async def permission_checker(
        current_user: CurrentUserResponse = Depends(get_current_user)
    ):
        user_permissions = getattr(current_user, "permissions", [])

        if not any(p in user_permissions for p in required_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission for notifications"
            )

        return current_user

    return permission_checker