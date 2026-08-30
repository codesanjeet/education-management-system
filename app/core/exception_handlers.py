from fastapi import Request, status
from fastapi.responses import JSONResponse
from .exceptions import (
    UserNotFoundException, 
    UserAlreadyExistsError, 
    DatabaseError,
    ClassNotFoundError,
    ClassCapacityExceededError,
    DuplicateRollNumberError,
    InvalidUserRoleError,
    # CLASS
    ClassNotFoundError,
    ClassAlreadyExistsError,
    InstitutionNotFoundError,
    ScheduleNotFoundError,
    ScheduleConflictError,
    # STAFF
    InvalidRoleError,
    StaffNotFoundError,
    InvalidStaffRoleError,
    # STUDY MATERIAL
    FileUploadError,
    InvalidFileTypeError,
    FileTooLargeError,
    StudyMaterialNotFoundError,
    # INSTITUTION
    InstitutionAlreadyExistsError,
    InvalidImageError,
    ImageTooLargeError,
    InsufficientPermissionError,
    RemarkNotFoundError,
    DisciplinaryRecordNotFoundError,
    DuplicateFeeStructureError,
    NotFoundError,
    BadRequestError,
    RateLimitExceededError
)
import logging

logger = logging.getLogger(__name__)


async def user_not_found_handler(request: Request, exc: UserNotFoundException):
    logger.warning(f"User not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Student not found"}
    )


async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
    logger.warning(f"Duplicate user: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "A student with this email already exists"}
    )


async def class_not_found_handler(request: Request, exc: ClassNotFoundError):
    logger.warning(f"Class not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Class not found"}
    )


async def class_capacity_handler(request: Request, exc: ClassCapacityExceededError):
    logger.info(f"Class capacity exceeded: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc) if "class" in str(exc).lower() else "Class is full"}
    )


async def duplicate_roll_handler(request: Request, exc: DuplicateRollNumberError):
    logger.warning(f"Duplicate roll number: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Roll number is already assigned"}
    )

async def duplicate_fee_structure_handler(request: Request, exc: DuplicateFeeStructureError):
    logger.warning(f"Duplicate fee structure: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Fee structure with this name and class already exists"}
    )


async def invalid_role_handler(request: Request, exc: InvalidUserRoleError):
    logger.warning(f"Invalid user role: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "User is not a student"}
    )


async def database_error_handler(request: Request, exc: DatabaseError):
    logger.error(f"Database error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Unable to process request. Please check your data"}
    )


async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)}
    )


async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later"}
    )


# FOR CLASSES 
async def class_not_found_handler(request: Request, exc: ClassNotFoundError):
    logger.warning(f"Class not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Class not found"}
    )


async def class_already_exists_handler(request: Request, exc: ClassAlreadyExistsError):
    logger.warning(f"Class already exists: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Class with this code already exists"}
    )


async def institution_not_found_handler(request: Request, exc: InstitutionNotFoundError):
    logger.warning(f"Institution not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Institution not found"}
    )


async def schedule_not_found_handler(request: Request, exc: ScheduleNotFoundError):
    logger.warning(f"Schedule not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Schedule not found"}
    )


async def schedule_conflict_handler(request: Request, exc: ScheduleConflictError):
    logger.warning(f"Schedule conflict: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)}
    )

# STAFF

async def invalid_role_handler(request: Request, exc: InvalidRoleError):
    logger.warning(f"Invalid role: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "User does not have the required role"}
    )


async def staff_not_found_handler(request: Request, exc: StaffNotFoundError):
    logger.warning(f"Staff not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Staff member not found"}
    )


async def invalid_staff_role_handler(request: Request, exc: InvalidStaffRoleError):
    logger.warning(f"Invalid staff role: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "User is not a staff member"}
    )


# Study material

async def file_upload_error_handler(request: Request, exc: FileUploadError):
    logger.error(f"File upload error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Failed to upload file"}
    )


async def invalid_file_type_handler(request: Request, exc: InvalidFileTypeError):
    logger.warning(f"Invalid file type: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Only images (JPG, PNG, WEBP) and PDF files are allowed"}
    )


async def file_too_large_handler(request: Request, exc: FileTooLargeError):
    logger.warning(f"File too large: {exc}")
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={"detail": "File too large. Maximum size is 100MB"}
    )


async def study_material_not_found_handler(request: Request, exc: StudyMaterialNotFoundError):
    logger.warning(f"Study material not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Study material not found"}
    )




# INSTITUTION

async def institution_already_exists_handler(request: Request, exc: InstitutionAlreadyExistsError):
    logger.warning(f"Institution already exists: {exc}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Institution with this email already exists"}
    )


async def invalid_image_handler(request: Request, exc: InvalidImageError):
    logger.warning(f"Invalid image: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Invalid image file. Only JPG, PNG, and WEBP are allowed"}
    )


async def image_too_large_handler(request: Request, exc: ImageTooLargeError):
    logger.warning(f"Image too large: {exc}")
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={"detail": "Image too large. Maximum size is 5MB"}
    )


async def insufficient_permission_handler(request: Request, exc: InsufficientPermissionError):
    logger.warning(f"Insufficient permission: {exc}")
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": "You don't have permission for this operation"}
    )
async def disciplinary_record_not_found_handler(request: Request, exc: DisciplinaryRecordNotFoundError):
    logger.warning(f"Disciplinary record not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Disciplinary record not found"}
    )
async def remark_not_found_handler(request: Request, exc: RemarkNotFoundError):
    logger.warning(f"Remark not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Remark not found"}
    )
async def not_found_handler(request: Request, exc: NotFoundError):
    logger.warning(f"Resource not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Resource not found"}
    )
async def bad_request_handler(request: Request, exc: BadRequestError):
    logger.warning(f"Bad request: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Bad request. Please check your data and try again"}
    )
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceededError):
    logger.warning(f"Rate limit exceeded: {exc}")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded. Please try again later"}
    )