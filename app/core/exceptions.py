class UserNotFoundException(Exception):
    pass
class UserAlreadyExistsError(Exception):
    pass
class DatabaseError(Exception):
    pass
class InsufficientPermissionError(Exception):
    pass
class InvalidUserRoleError(Exception):
    pass

class ClassCapacityExceededError(DatabaseError):
    """Raised when class has no available seats"""
    pass

class DuplicateRollNumberError(DatabaseError):
    """Raised when roll number already exists in class"""
    pass

class ClassNotFoundError(DatabaseError):
    """Raised when class doesn't exist"""
    pass

class InvalidRoleError(ValueError):
    """Raised when user has wrong role for operation"""
    pass


class StorageLimitExceededError(Exception):
    """
    Raised when an upload would push an institution over storage cap.
    Mapped to HTTP 507 Insufficient Storage in the router's _handle_crud_exc.
    """
    pass

# FOR CLASS

class ClassNotFoundError(DatabaseError):
    """Class not found or unavailable"""
    pass

class ClassAlreadyExistsError(DatabaseError):
    """Class with this code already exists"""
    pass

class InstitutionNotFoundError(DatabaseError):
    """Institution not found"""
    pass

class ScheduleNotFoundError(DatabaseError):
    """Schedule not found"""
    pass

class ScheduleConflictError(DatabaseError):
    """Schedule time conflict"""
    pass


# Staff

class InvalidRoleError(Exception):
    """User does not have the required role for this operation"""
    pass

class StaffNotFoundError(UserNotFoundException):
    """Staff member not found"""
    pass

class InvalidStaffRoleError(InvalidRoleError):
    """User is not a staff member"""
    pass

# Study material

class FileUploadError(Exception):
    """File upload operation failed"""
    pass

class InvalidFileTypeError(Exception):
    """Invalid file type uploaded"""
    pass

class FileTooLargeError(Exception):
    """Uploaded file exceeds size limit"""
    pass

class StudyMaterialNotFoundError(UserNotFoundException):
    """Study material not found"""
    pass

# INSTITUTION

class InstitutionAlreadyExistsError(Exception):
    """Institution with this email already exists"""
    pass

class InvalidImageError(Exception):
    """Invalid image file"""
    pass

class ImageTooLargeError(Exception):
    """Image file exceeds size limit"""
    pass







# ── Add these two entries to your existing core/exceptions.py ──────────────

class RemarkNotFoundError(DatabaseError):
    """Remark not found"""
    pass

class DisciplinaryRecordNotFoundError(DatabaseError):
    """Disciplinary record not found"""
    pass


# fee related exceptions
class DuplicateFeeStructureError(DatabaseError):
    """Raised when fee structure with same name and class already exists"""
    pass
class NotFoundError(DatabaseError):
    """Resource not found"""
    pass
class BadRequestError(DatabaseError):
    """Bad request error"""
    pass
class RateLimitExceededError(Exception):
    """Rate limit exceeded"""
    pass