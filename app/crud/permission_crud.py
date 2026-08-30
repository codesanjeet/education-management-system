from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from ..models.permission_model import PermissionDB, UserPermissionDB
from ..schemas.permission_schema import (
    PermissionEnum,
    UserPermissionsResponse,
    PermissionDetail,
    AssignPermissionsResponse,
    UpdatePermissionsResponse,
    AvailablePermissionsResponse
)



# ============================================================================
# Custom Exceptions
# ============================================================================

class PermissionNotFoundError(Exception):
    """Raised when permission is not found"""
    pass


# ============================================================================
# Helper Functions
# ============================================================================

async def _get_permission_by_name(
    db: AsyncSession,
    permission_name: str
) -> Optional[PermissionDB]:
    """Get permission by name"""
    stmt = select(PermissionDB).where(PermissionDB.name == permission_name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ============================================================================
# CRUD Operations
# ============================================================================

async def assign_permissions_to_user(
    db: AsyncSession,
    user_id: int,
    permissions: List[PermissionEnum],
    granted_by: int
) -> AssignPermissionsResponse:
    """
    Assign permissions to a user (adds to existing permissions)
    
    Args:
        db: Database session
        user_id: ID of the user to assign permissions to (already verified via JWT)
        permissions: List of permission enums to assign
        granted_by: ID of the user granting permissions
        
    Returns:
        AssignPermissionsResponse with assigned permissions
        
    Raises:
        PermissionNotFoundError: If permission doesn't exist
        SQLAlchemyError: If database operation fails
    """
    # if instance of enum ok if not make it 
    permissions = [
        p if isinstance(p, PermissionEnum) else PermissionEnum(p)
        for p in permissions
    ]
    try:
        assigned_permissions = []
        skipped_permissions = []
        
        for perm_enum in permissions:
            # Get permission from database
            permission = await _get_permission_by_name(db, perm_enum.value)
            
            if not permission:
                raise PermissionNotFoundError(
                    f"Permission '{perm_enum.value}' not found in database"
                )
            
            # Check if permission already exists
            check_stmt = select(UserPermissionDB).where(
                UserPermissionDB.user_id == user_id,
                UserPermissionDB.permission_id == permission.id
            )
            existing = await db.execute(check_stmt)
            
            if existing.scalar_one_or_none():
                skipped_permissions.append(perm_enum.value)
                continue  # Skip if already assigned
            
            # Create new user permission
            user_permission = UserPermissionDB(
                user_id=user_id,
                permission_id=permission.id,
                granted_by=granted_by,
                granted_at=datetime.utcnow()
            )
            
            db.add(user_permission)
            assigned_permissions.append(perm_enum.value)
        
        await db.commit()
        
        message = f"Successfully assigned {len(assigned_permissions)} permission(s)"
        if skipped_permissions:
            message += f". Skipped {len(skipped_permissions)} already assigned permission(s)"
        
        return AssignPermissionsResponse(
            success=True,
            message=message,
            user_id=user_id,
            assigned_permissions=assigned_permissions,
            total_assigned=len(assigned_permissions)
        )
        
    except PermissionNotFoundError:
        await db.rollback()
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise SQLAlchemyError(f"Failed to assign permissions: {str(e)}")


async def update_user_permissions(
    db: AsyncSession,
    user_id: int,
    permissions: List[PermissionEnum],
    granted_by: int
) -> UpdatePermissionsResponse:
    """
    Update user permissions (replaces all existing permissions)
    
    Args:
        db: Database session
        user_id: ID of the user (already verified via JWT)
        permissions: Complete list of permissions to set
        granted_by: ID of the user granting permissions
        
    Returns:
        UpdatePermissionsResponse with current permissions
        
    Raises:
        PermissionNotFoundError: If permission doesn't exist
        SQLAlchemyError: If database operation fails
    """
    try:
        # Delete all existing permissions
        delete_stmt = delete(UserPermissionDB).where(
            UserPermissionDB.user_id == user_id
        )
        await db.execute(delete_stmt)
        
        # Assign new permissions
        current_permissions = []
        
        for perm_enum in permissions:
            permission = await _get_permission_by_name(db, perm_enum.value)
            
            if not permission:
                raise PermissionNotFoundError(
                    f"Permission '{perm_enum.value}' not found in database"
                )
            
            user_permission = UserPermissionDB(
                user_id=user_id,
                permission_id=permission.id,
                granted_by=granted_by,
                granted_at=datetime.utcnow()
            )
            
            db.add(user_permission)
            current_permissions.append(perm_enum.value)
        
        await db.commit()
        
        return UpdatePermissionsResponse(
            success=True,
            message=f"Successfully updated permissions for user {user_id}",
            user_id=user_id,
            current_permissions=current_permissions,
            total_permissions=len(current_permissions)
        )
        
    except PermissionNotFoundError:
        await db.rollback()
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise SQLAlchemyError(f"Failed to update permissions: {str(e)}")


async def get_user_permissions(
    db: AsyncSession,
    user_id: int
) -> UserPermissionsResponse:
    """
    Get all permissions for a specific user
    
    Args:
        db: Database session
        user_id: ID of the user (already verified via JWT)
        
    Returns:
        UserPermissionsResponse with all user permissions
        
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        # Get user permissions with eager loading
        stmt = (
            select(UserPermissionDB)
            .options(selectinload(UserPermissionDB.permission))
            .where(UserPermissionDB.user_id == user_id)
            .order_by(UserPermissionDB.granted_at.desc())
        )
        
        result = await db.execute(stmt)
        user_permissions = result.scalars().all()
        
        # Build permission details
        permission_details = [
            PermissionDetail(
                id=up.permission.id,
                name=up.permission.name,
                description=up.permission.description,
                granted_at=up.granted_at,
                granted_by=up.granted_by
            )
            for up in user_permissions
        ]
        
        return UserPermissionsResponse(
            user_id=user_id,
            permissions=permission_details,
            total_permissions=len(permission_details)
        )
        
    except SQLAlchemyError as e:
        raise SQLAlchemyError(f"Failed to retrieve permissions: {str(e)}")


async def get_all_available_permissions(
    db: AsyncSession
) -> AvailablePermissionsResponse:
    """
    Get all available permissions in the system grouped by category
    
    Args:
        db: Database session
        
    Returns:
        AvailablePermissionsResponse with all available permissions
        
    Raises:
        SQLAlchemyError: If database operation fails
    """
    try:
        stmt = select(PermissionDB).order_by(PermissionDB.name)
        result = await db.execute(stmt)
        permissions = result.scalars().all()
        
        # Group by category
        categories = set()
        permission_list = []
        
        for perm in permissions:
            category = perm.name.split(':')[0]
            categories.add(category)
            
            permission_list.append({
                "id": perm.id,
                "name": perm.name,
                "description": perm.description,
                "category": category
            })
        
        return AvailablePermissionsResponse(
            permissions=permission_list,
            total=len(permission_list),
            categories=sorted(list(categories))
        )
        
    except SQLAlchemyError as e:
        raise SQLAlchemyError(f"Failed to retrieve available permissions: {str(e)}")
    

