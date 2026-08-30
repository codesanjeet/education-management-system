# ══════════════════════════════════════════════════════════════════════════════
# CLASS
# ══════════════════════════════════════════════════════════════════════════════

# Any permission whose workflow requires reading class data
CLASS_READ_PERMISSIONS = (
    "class:view",
    "class:management",
    "student:create",
    "student:update",
    "student:view_class",
    "student:view",
    "attendance:student_attendance_management",
    "staff:create",
    "staff:view",
    "staff:view_all",
    "content:basic_management",
    "content:full_management",
    "exam:full_management",
    "notification:admin_level",
    "notification:all_staff_level",
)

# Any permission whose workflow requires writing/managing classes
CLASS_WRITE_PERMISSIONS = (
    "class:management",
)


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT
# ══════════════════════════════════════════════════════════════════════════════

# Any permission whose workflow requires reading student list / profile
STUDENT_READ_PERMISSIONS = (
    "student:view",
    "student:view_class",
    "student:create",
    "student:update",
    "attendance:student_attendance_management",
    "fee:collection",
    "fee:report",
    "notification:admin_level",
    "notification:all_staff_level",
    "exam:full_management",
    "discipline:management",
    "recycle_bin:user"
)

# Any permission whose workflow requires writing student data
STUDENT_WRITE_PERMISSIONS = (
    "student:create",
    "student:update",
)


# ══════════════════════════════════════════════════════════════════════════════
# STAFF
# ══════════════════════════════════════════════════════════════════════════════

# Any permission whose workflow requires reading staff list / profile
STAFF_READ_PERMISSIONS = (
    "staff:view",
    "staff:view_all",
    "staff:create",
    "staff:update",
    "class:management",
    "attendance:staff_attendance_management",
    "notification:admin_level",
    "permission:manage",
    "recycle_bin:user"
)

# Any permission whose workflow requires writing staff data
STAFF_WRITE_PERMISSIONS = (
    "staff:create",
    "staff:update",
)


# ══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE
# ══════════════════════════════════════════════════════════════════════════════

# Any permission whose workflow requires reading student attendance
STUDENT_ATTENDANCE_READ_PERMISSIONS = (
    "attendance:student_attendance_management",
    "notification:admin_level",
    "fee:report",
    "exam:full_management",
)

# Any permission whose workflow requires reading staff attendance
STAFF_ATTENDANCE_READ_PERMISSIONS = (
    "attendance:staff_attendance_management",
    "notification:admin_level",
)


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION
# ══════════════════════════════════════════════════════════════════════════════

# Any permission that can send / manage notifications
NOTIFICATION_READ_PERMISSIONS = (
    "notification:admin_level",
    "notification:all_staff_level",
    "notification:student_level",
)

NOTIFICATION_ADMIN_PERMISSIONS = (
    "notification:admin_level",
)


# ══════════════════════════════════════════════════════════════════════════════
# FEE
# ══════════════════════════════════════════════════════════════════════════════

# Any permission whose workflow requires reading fee / invoice data
FEE_READ_PERMISSIONS = (
    "fee:collection",
    "fee:report",
    "fee:structure_manage",
)

FEE_WRITE_PERMISSIONS = (
    "fee:collection",
    "fee:structure_manage",
)


# ══════════════════════════════════════════════════════════════════════════════
# EXAM
# ══════════════════════════════════════════════════════════════════════════════

EXAM_READ_PERMISSIONS = (
    "exam:full_management",
    "exam:view",
    "notification:admin_level",
)

EXAM_WRITE_PERMISSIONS = (
    "exam:full_management",
)


# ══════════════════════════════════════════════════════════════════════════════
# STUDY MATERIAL / CONTENT
# ══════════════════════════════════════════════════════════════════════════════

CONTENT_READ_PERMISSIONS = (
    "content:basic_management",
    "content:full_management",
    "student:view_class",        # students can read materials for their class
    "notification:all_staff_level",
)

CONTENT_WRITE_PERMISSIONS = (
    "content:basic_management",
    "content:full_management",
)


# ══════════════════════════════════════════════════════════════════════════════
# AI AGENT
# ══════════════════════════════════════════════════════════════════════════════

AI_MANAGE_PERMISSIONS = (
    "voice_agent:ai_voice_agent_manage",
)


# ══════════════════════════════════════════════════════════════════════════════
# DISCIPLINE
# ══════════════════════════════════════════════════════════════════════════════

DISCIPLINE_READ_PERMISSIONS = (
    "discipline:management",
    "notification:admin_level",
    "student:view",
)

DISCIPLINE_WRITE_PERMISSIONS = (
    "discipline:management",
)


# ══════════════════════════════════════════════════════════════════════════════
# PERMISSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

PERMISSION_MANAGE_PERMISSIONS = (
    "permission:manage",
)


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

SETTINGS_WRITE_PERMISSIONS = (
    "system:settings",
)

# Read-only settings (billing, general info) — wider audience
SETTINGS_READ_PERMISSIONS = (
    "system:settings",
    "fee:collection",
    "fee:report",
    "notification:admin_level",
)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

DASHBOARD_READ_PERMISSIONS = (
    "recent_activity_logs:view",
    "notification:admin_level",
    "system:settings",
)