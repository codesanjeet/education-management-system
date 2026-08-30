from fastapi import FastAPI,Depends
from fastapi.middleware.cors import CORSMiddleware 
from .core.database import test_connection
from .routers.institution_route import router as institution_router
from .routers.staff_router import router as teacher_router
# from fastapi.staticfiles import StaticFiles
from .routers.student_router import router as student_router
from .routers.class_router import router as class_router
from .routers.attendance_router import router as attendance_router
from .routers.study_material_router import router as study_material_router
from .routers.class_room_router import router as class_room_router
from .routers.notification_router import router as announcement_router
from .routers.setting_router import router as setting_router
from .routers.auth_router import router as auth_router
from .routers.permission_router import router as perm_router
from .routers.remarks_router import router as remarks_router
from .routers.fee_router import router as fee_router
from .routers.notification_router import automation_router
from .routers.admission_router import router as admission_router
from .routers.ai_agent_router import router as ai_agent_router
from .routers.super_admin_router import router as super_admin_router
from .schemas.user_schema import CurrentUserResponse
from .deps import get_current_user
from .routers.system_ai_agent_router import router as system_ai_agent_router
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# exception
from app.core.exception_handlers import (
    user_not_found_handler,
    user_already_exists_handler,
    class_not_found_handler,
    class_capacity_handler,
    duplicate_roll_handler,
    invalid_role_handler,
    database_error_handler,
    value_error_handler,
    general_exception_handler,
    # FOR CLASS 
    class_not_found_handler,
    class_already_exists_handler,
    institution_not_found_handler,
    schedule_not_found_handler,
    schedule_conflict_handler,
    # STAFF
    invalid_role_handler,
    staff_not_found_handler,
    invalid_staff_role_handler,
    file_upload_error_handler,
    invalid_file_type_handler,
    file_too_large_handler,
    study_material_not_found_handler,
    # INSTITUTION
    institution_already_exists_handler,
    invalid_image_handler,
    image_too_large_handler,
    insufficient_permission_handler,
    duplicate_fee_structure_handler,
    not_found_handler,
    bad_request_handler,
    rate_limit_exceeded_handler
    
)
from app.core.exceptions import (
    UserNotFoundException,
    UserAlreadyExistsError,
    ClassNotFoundError,
    ClassCapacityExceededError,
    DuplicateRollNumberError,
    InvalidUserRoleError,
    DatabaseError,
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
    # INTITUTION
    InstitutionAlreadyExistsError,
    InvalidImageError,
    ImageTooLargeError,
    InsufficientPermissionError,
    DuplicateFeeStructureError,
    RateLimitExceededError,
    NotFoundError,
    BadRequestError
    
)
# from routers.user_route import router as user_router

app = FastAPI()

# Excepitons
app.add_exception_handler(UserNotFoundException, user_not_found_handler)
app.add_exception_handler(UserAlreadyExistsError, user_already_exists_handler)
app.add_exception_handler(ClassNotFoundError, class_not_found_handler)
app.add_exception_handler(ClassCapacityExceededError, class_capacity_handler)
app.add_exception_handler(DuplicateRollNumberError, duplicate_roll_handler)
app.add_exception_handler(InvalidUserRoleError, invalid_role_handler)
app.add_exception_handler(DatabaseError, database_error_handler)
app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(Exception, general_exception_handler)
# FOR CLASS
app.add_exception_handler(ClassNotFoundError, class_not_found_handler)
app.add_exception_handler(ClassAlreadyExistsError, class_already_exists_handler)
app.add_exception_handler(InstitutionNotFoundError, institution_not_found_handler)
app.add_exception_handler(ScheduleNotFoundError, schedule_not_found_handler)
app.add_exception_handler(ScheduleConflictError, schedule_conflict_handler)
# FOR STAFF
app.add_exception_handler(InvalidRoleError, invalid_role_handler)
app.add_exception_handler(StaffNotFoundError, staff_not_found_handler)
app.add_exception_handler(InvalidStaffRoleError, invalid_staff_role_handler)
# STUDY MATERIAL 
app.add_exception_handler(FileUploadError, file_upload_error_handler)
app.add_exception_handler(InvalidFileTypeError, invalid_file_type_handler)
app.add_exception_handler(FileTooLargeError, file_too_large_handler)
app.add_exception_handler(StudyMaterialNotFoundError, study_material_not_found_handler)
# INSTITUTION
app.add_exception_handler(InstitutionAlreadyExistsError, institution_already_exists_handler)
app.add_exception_handler(InvalidImageError, invalid_image_handler)
app.add_exception_handler(ImageTooLargeError, image_too_large_handler)
# fee
app.add_exception_handler(DuplicateFeeStructureError, duplicate_fee_structure_handler)
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(BadRequestError, bad_request_handler)
app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)
# Configure CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "http://192.168.1.4:3000",

        
    ],
    allow_credentials=True,  # Allow cookies and authentication headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS","PATCH",], 
    allow_headers=["*"],  # Allow all headers (or specify specific ones)
)

# Include routers AFTER CORS middleware
app.include_router(student_router, prefix="/api", tags=["Students"])
app.include_router(institution_router, prefix="/api", tags=["Institutions"])
app.include_router(fee_router, prefix="/api", tags=["Fees"])
app.include_router(class_router, prefix="/api", tags=["Classes"])
app.include_router(attendance_router, prefix="/api", tags=["Attendance"])
app.include_router(teacher_router, prefix="/api", tags=["Staffs"])
app.include_router(study_material_router, prefix="/api", tags=["Study Materials"])
app.include_router(class_room_router, prefix="/api", tags=["ClassRooms"])
app.include_router(announcement_router, prefix="/api",tags=["Notifications"])
app.include_router(automation_router, prefix="/api", tags=["Automation"])
app.include_router(setting_router, prefix="/api", tags=["Settings"])
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(admission_router, prefix="/api", tags=["Admissions"])
app.include_router(remarks_router, prefix="/api", tags=["Remarks"])
app.include_router(ai_agent_router, prefix="/api", tags=["AI Agents"])
app.include_router(super_admin_router, prefix="/api", tags=["Super Admin"])
app.include_router(perm_router, prefix="/api")
app.include_router(system_ai_agent_router, prefix="/api", tags=["System AI"])
app.add_exception_handler(InsufficientPermissionError, insufficient_permission_handler)
# app.include_router(user_router, prefix="/api", tags=["Users"])



# for current 
@app.get("/api/institutions/users/me", response_model=CurrentUserResponse)
async def get_me(current_user: CurrentUserResponse = Depends(get_current_user)):
    """
    Get currently authenticated user
    """
    return current_user



# Run the connection test when the app starts
@app.on_event("startup")
async def on_startup():
    await test_connection()

# app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Health check endpoint for production
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}



