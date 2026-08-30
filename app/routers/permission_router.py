from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from ..schemas.user_schema import CurrentUserResponse
from ..core.database import get_db
from ..deps import get_current_user, require_permission
from ..crud import permission_crud
from ..schemas.permission_schema import (
    AssignPermissionsRequest,
    UpdatePermissionsRequest,
    UserPermissionsResponse,
    AssignPermissionsResponse,
    UpdatePermissionsResponse,
    AvailablePermissionsResponse
)
from ..crud.user_fun import get_basic_user_by_id
from ..crud.dashboard_crud import create_recent_activity_log
router = APIRouter(
    prefix="/permissions",
    tags=["Permissions Management"]
)


@router.post(
    "/assign",
    response_model=AssignPermissionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign permissions to a user",
    description="Add new permissions to a user (does not remove existing permissions)"
)
async def assign_permissions(
    request: AssignPermissionsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserResponse, Depends(get_current_user)],
    _: Annotated[None, Depends(require_permission("permission:manage"))]
):
    """
    Assign permissions to a user
    
    **Required Permission:** `permission:manage`
    
    """
    try:
        response = await permission_crud.assign_permissions_to_user(
            db=db,
            user_id=request.user_id,
            permissions=request.permissions,
            granted_by=current_user.id
        )
        return response
        
    except permission_crud.PermissionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign permissions: {str(e)}"
        )


@router.put(
    "/update/{user_id}",
    response_model=UpdatePermissionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user permissions",
    description="Replace all user permissions with a new set (complete override)"
)
async def update_permissions(
    user_id: int,
    request: UpdatePermissionsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserResponse, Depends(require_permission("permission:manage"))]
):
    """
    Update user permissions (replaces all existing permissions)
    
    **Required Permission:** `permission:manage`
    
    **Warning:** This completely replaces existing permissions
    """
    try:
        response = await permission_crud.update_user_permissions(
            db=db,
            user_id=user_id,
            permissions=request.permissions,
            granted_by=current_user.id
        )
        user = await get_basic_user_by_id(db=db, id=user_id, tenant_id=current_user.tenant_id) # to get user info for activity log

        await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="permission_updated",
        message=f"Permissions updated for user:{user.email}(critical action)"
    )
        return response
        
    except permission_crud.PermissionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update permissions: {str(e)}"
        )


@router.get(
    "/user/{user_id}",
    response_model=UserPermissionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user permissions",
    description="Retrieve all permissions assigned to a specific user"
)
async def get_user_permissions(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserResponse, Depends(get_current_user)]
):
    """
    Get all permissions for a user
    
    **Note:** Users can view their own permissions, or if they have permission:manage they can view any user
    """
    try:
        # Check if user is viewing their own permissions OR has permission:manage
        if user_id != current_user.id:
            # Check if user has permission:manage
            if "permission:manage" not in current_user.permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only view your own permissions"
                )
        
        response = await permission_crud.get_user_permissions(
            db=db,
            user_id=user_id
        )
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve permissions: {str(e)}"
        )


@router.get(
    "/available",
    response_model=AvailablePermissionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all available permissions",
    description="Retrieve all permissions available in the system grouped by category"
)
async def get_available_permissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserResponse, Depends(get_current_user)],
    # _: Annotated[None, Depends(require_permission("permission:manage"))]
):
    """
    Get all available permissions
    
    **Required Permission:** `permission:manage`
    """
    try:
        response = await permission_crud.get_all_available_permissions(db=db)
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve available permissions: {str(e)}"
        )