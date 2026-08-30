from app.core.security import get_password_hash, verify_password
import secrets
from datetime import datetime , timedelta
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_,func
from app.models.user_model import UserDB
from app.models.institution_model import InstitutionDB
from pydantic import EmailStr
from typing import Optional
from ..core.exceptions import UserNotFoundException
from datetime import datetime,timezone
from ..models.user_model import UserSecurityDB,UserDB,UserLogDB
from sqlalchemy.orm import selectinload
from ..services.user import get_valid_user
from ..models.user_model import UserSessionDB

from datetime import datetime
from ..schemas.user_schema import UsersBasicResponse

from sqlalchemy import select, func



async def generate_unique_username(
    db: AsyncSession,
    names: list[tuple[str, str]]
) -> list[str]:
    candidates_per_student = []
    all_candidates = []

    for first_name, last_name in names:
        base = f"{first_name.lower().strip()}.{last_name.lower().strip()}"
        candidates = [f"{base}{secrets.randbelow(100000):05d}" for _ in range(10)]
        candidates_per_student.append(candidates)
        all_candidates.extend(candidates)

    result = await db.execute(
        select(UserDB.user_name).where(UserDB.user_name.in_(all_candidates))
    )
    taken = {row[0] for row in result.all()}

    usernames = []
    for i, candidates in enumerate(candidates_per_student):
        chosen = next((c for c in candidates if c not in taken), None)
        if not chosen:
            first, last = names[i]
            chosen = f"{first.lower()}.{last.lower()}{int(datetime.utcnow().timestamp())}{i}"
        taken.add(chosen)
        usernames.append(chosen)

    return usernames


# MARK AS DELETE user
async def mark_as_deleted_user(db: AsyncSession, tenant_id: str, user_id: int, restore: bool):


    user_query = await db.execute(select(UserDB).where(
     UserDB.id == user_id, UserDB.tenant_id == tenant_id
    ))
    user_to_delete = user_query.scalars().first()
    if not user_to_delete:
        raise UserNotFoundException(
            f"user with Tenant ID {tenant_id} and User ID { user_id} not found"
        ) 

    if user_to_delete.deleted_date is None and restore == False:
        user_to_delete.deleted_date = datetime.now(timezone.utc).date()
        message = f"User has been soft-deleted."
    else:
        user_to_delete.deleted_date = None
        message = f"User has been restored."
    

    await db.commit()
    await db.refresh(user_to_delete)
    
    return user_to_delete


# DELETE user
async def delete_user(db: AsyncSession, tenant_id: str, email: Optional[EmailStr] = None, user_name: Optional[str] = None):
    query1 = await db.execute(select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id))
    instituion = query1.scalars().first()
    if not instituion:
        raise Exception(f"Instition no found with the tenant id {tenant_id}")
    
    if not email and not user_name:
        raise Exception("You need to provide at least one: email or user_name")

    conditions = []

    if email:
        normalized_email = email.lower()
        conditions.append(UserDB.email == normalized_email)

    if user_name:
        normalized_user_name = user_name.lower()
        conditions.append(UserDB.user_name == normalized_user_name)

    query2 = await db.execute(select(UserDB).where(
     *conditions
    ))
    user_to_delete = query2.scalars().first()
    if not user_to_delete:
        raise UserNotFoundException(
            f"Class with Tenant ID {tenant_id} and class_name {user_name or email} not found"
        ) 
    await db.delete(user_to_delete)
    return {"message": f"deleted successfully"}






# FOR AUTH ALL BELOW
async def check_tenant_id_by_identifier(
    db: AsyncSession,
    identifier: str
):
    normalized_identifier = identifier.lower()

    stmt = (
        select(
            UserDB.tenant_id,
            InstitutionDB.institute_name,
            InstitutionDB.logo
        )
        .join(InstitutionDB, InstitutionDB.id == UserDB.institution_id)
        .where(
            or_(
                UserDB.email == normalized_identifier,
                UserDB.user_name == normalized_identifier
            )
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return {
            "exists": False,
            "identifier": normalized_identifier,
            "institutions": []
        }

    return {
        "exists": True,
        "identifier": normalized_identifier,
        "institutions": [
            {
                "tenant_id": row.tenant_id,
                "name": row.institute_name,
                "logo": row.logo,
            }
            for row in rows
        ]
    }


async def get_user_by_username_or_email(
    db: AsyncSession,
    identifier: str,
    tenant_id: str
) -> UserDB | None:

    normalized_identifier = identifier.lower()

    stmt = (
        select(UserDB)
        .options(
            selectinload(UserDB.security),
            selectinload(UserDB.institution)
        )
        .join(InstitutionDB, InstitutionDB.id == UserDB.institution_id)
        .where(
            or_(
                UserDB.user_name == normalized_identifier,
                UserDB.email == normalized_identifier
            ),
            UserDB.tenant_id == tenant_id,
            InstitutionDB.is_verified == True,
            InstitutionDB.is_block == False,
            InstitutionDB.deleted_date == None,
            UserDB.deleted_date == None,
        )
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    return user

async def get_basic_user_by_id(
    db: AsyncSession,
    id: int,
    tenant_id: str
) -> UsersBasicResponse:


    stmt = (
        select(UserDB)
        .where(
            UserDB.id == id,
            UserDB.tenant_id == tenant_id,
            UserDB.deleted_date == None
        )
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    return user
    





async def authenticate_user(
    db: AsyncSession,
    identifier: str,
    password: str,
    tenant_id: str
) -> Optional[UserDB]:
    

    user = await get_valid_user(db=db, identifier=identifier,tenant_id=tenant_id)
    
    if not user:
        return None
    
    if not user.security.password_hash:
        # User only has Google login
        return None
    
    if not verify_password(password, user.security.password_hash):
        return None
    
    return user





async def activate_user_with_password(
    db: AsyncSession,
    activation_token: str,
    password: str
) -> Optional[UserDB]:

    stmt = (
        select(UserSecurityDB)
        .options(selectinload(UserSecurityDB.user))
        .where(
            UserSecurityDB.activation_token == activation_token,
            UserSecurityDB.activation_token_expires > datetime.utcnow()
        )
        .with_for_update()   # race-condition safe
    )

    result = await db.execute(stmt)
    security = result.scalars().first()

    if not security or not security.user:
        return None

    # security-related changes
    security.password_hash = get_password_hash(password)
    security.activated_at = datetime.utcnow()
    security.activation_token = None
    security.activation_token_expires = None

    # account-level activation
    security.user.is_active = True

    await db.commit()
    await db.refresh(security.user)

    return security.user



# Related to Session
async def session_db_create_for_refresh_token(
    user_id: int,
    jti: str,
    expires_at: datetime,
    ip_address: str,
    user_agent: str,
    db: AsyncSession
) -> None: 
    user_session = UserSessionDB(
        user_id=user_id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
        last_used_at=datetime.utcnow(),
        revoked=False
    )
    
    db.add(user_session)
    await db.commit()


async def session_db_check_valid(
    jti: str,
    db: AsyncSession
) -> bool:
    """
    Check if session is valid (not revoked, not expired)
    """
    result = await db.execute(
        select(UserSessionDB).where(
            UserSessionDB.jti == jti,
            UserSessionDB.revoked == False,
            UserSessionDB.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()
    return session is not None


async def session_db_revoke(
    jti: str,
    db: AsyncSession
) -> bool:
    """
    Revoke a session (logout)
    """
    result = await db.execute(
        select(UserSessionDB).where(UserSessionDB.jti == jti)
    )
    session = result.scalar_one_or_none()
    
    if session:
        session.revoked = True
        await db.commit()
        return True
    
    return False


async def session_db_update_last_used(
    jti: str,
    db: AsyncSession
):
    """
    Update last_used_at timestamp
    """
    result = await db.execute(
        select(UserSessionDB).where(UserSessionDB.jti == jti)
    )
    session = result.scalar_one_or_none()
    
    if session:
        session.last_used_at = datetime.utcnow()
        await db.commit()


async def forgot_password(
        email: str,
        reset_token: str,
        reset_token_expires: datetime,
        db: AsyncSession
):
    stmt = select(UserSecurityDB).join(
        UserDB, UserSecurityDB.user_id == UserDB.id
    ).options(
        selectinload(UserSecurityDB.user)
    ).where(
        UserDB.email == email,
        UserDB.tenant_id ==   "TEN00001"
    )
    result = await db.execute(stmt)
    # user_security = result.scalar_one_or_none()
    user_security = result.scalars().first()

    
    if not user_security:
        raise Exception("User not found")

    user_security.password_reset_token = reset_token
    user_security.password_reset_expires = reset_token_expires

    await db.commit()
    await db.refresh(user_security)

    return UsersBasicResponse.model_validate(user_security.user)

async def reset_password(
        reset_token: str,
        new_password: str,
        db: AsyncSession
):
    stmt = select(UserSecurityDB).where(
         UserSecurityDB.password_reset_token == reset_token,
         UserSecurityDB.password_reset_expires > datetime.utcnow()
    )
    result = await db.execute(stmt)
    # user_security = result.scalar_one_or_none()
    user_security = result.scalars().first()

    if not user_security:
        return None
    # update the password

    user_security.password_hash = get_password_hash(new_password)
    user_security.password_reset_token = None
    user_security.password_reset_expires = None

    await db.commit()
    await db.refresh(user_security)

    return {"message": "Password reset successfully"}
 




# Auth GOOGLE

async def check_rate_limit_by_ip(
    db: AsyncSession,
    ip_address: str,
    max_attempts: int = 5,
    time_window_minutes: int = 10
) -> bool:
    """
    Check if IP has exceeded login attempts
    Uses your existing UserLogDB table
    
    Returns True if rate limited (too many attempts)
    """
    time_threshold = datetime.utcnow() - timedelta(minutes=time_window_minutes)
    
    query = select(func.count(UserLogDB.id)).where(
            UserLogDB.ip_address == ip_address,
            UserLogDB.login_time >= time_threshold,
            UserLogDB.success == False  # Only count failed attempts
    )
    
    result = await db.execute(query)
    attempt_count = result.scalar()
    
    return attempt_count >= max_attempts


async def log_login_attempt(
    db: AsyncSession,
    user_id: int = None,
    ip_address: str = None,
    user_agent: str = None,
    success: bool = True
):
    """
    Log login attempt using your existing UserLogDB
    """
    log_entry = UserLogDB(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        login_time=datetime.utcnow()
    )
    db.add(log_entry)
    await db.commit()


async def find_user_by_google_id(
    db: AsyncSession,
    google_id: str,
    tenant_id: str
) -> Optional[UserDB]:
    """
    Find user by Google ID and institution
    """
    query = select(UserDB).join(UserSecurityDB).options(
        selectinload(UserDB.security)).where(
            UserSecurityDB.google_id == google_id,
            UserDB.tenant_id == tenant_id
    )
    result = await db.execute(query)
    return result.scalars().first()


async def find_user_by_email_and_institution(
    db: AsyncSession,
    email: str,
    tenant_id: str
) -> Optional[UserDB]:
    """
    Find user by email and institution
    """
    query = select(UserDB).options(
        selectinload(UserDB.security)).where(
            UserDB.email == email.lower(),
            UserDB.tenant_id == tenant_id
    )
    result = await db.execute(query)
    return result.scalars().first()


async def link_google_account(
    db: AsyncSession,
    user: UserDB,
    google_id: str
) -> UserDB:
    """
    Link Google account to existing user
    """
    if not user.security:
        raise ValueError("User security record not found")
    
    user.security.google_id = google_id
    user.security.google_linked_at = datetime.utcnow()
    user.is_active = True  # Auto-activate on Google login
    
    await db.commit()
    await db.refresh(user)
    
    return user


# def get_user_by_google_id(db: AsyncSession, google_id: str) -> Optional[UserDB]:
#     """
#     Get user by Google ID
#     """
#     return db.query(UserDB).filter(UserDB.google_id == google_id).first()
