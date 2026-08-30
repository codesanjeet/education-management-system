DEFAULT_PERMISSIONS_ADMIN = [
    # ============================================================
    # SYSTEM ADMINISTRATION
    # ============================================================
    ("system:settings", "Manage system-wide settings and configurations"),
    ("user:role_manage", "Create, update, and delete user roles"),
    # ("permission:manage", "Assign and revoke permissions"),
    ("bulk:entry", "Perform bulk operations (import/export data)"),

    # ============================================================
    # STUDENT MANAGEMENT
    # ============================================================
    ("student:create", "Create new student records"),
    ("student:update", "Update existing student information"),
    ("student:delete", "Delete student records"),
    ("student:view", "View individual student details"),
    ("student:view_all", "View all students across all classes"),
    ("student:view_class", "View students within specific class only"),
    ("student:status_change", "Change student status (active/inactive/transferred)"),

    # ============================================================
    # STAFF MANAGEMENT
    # ============================================================
    ("staff:create", "Create new staff member records"),
    ("staff:update", "Update existing staff member information"),
    ("staff:delete", "Delete staff member records"),
    ("staff:view", "View individual staff member details"),
    ("staff:view_all", "View all staff members"),

    # ============================================================
    # CLASS MANAGEMENT
    # ============================================================
    ("class:management", "Full class management including CRUD operations, class schedules, and assignments"),

    # ============================================================
    # ATTENDANCE MANAGEMENT
    # ============================================================
    ("attendance:student_attendance_management", "Manage student attendance including marking, updating, and viewing attendance reports"),
    ("attendance:staff_attendance_management", "Manage staff attendance including marking, updating, and viewing attendance reports"),

    # ============================================================
    # EXAM & RESULT MANAGEMENT
    # ============================================================
    ("exam:full_management", "Manage exams including creating, scheduling, and editing (excludes grading and result publishing)"),
    ("grade:assign", "Assign and update grades for exams"),
    ("result:publish", "Publish exam results to students and parents"),
    ("result:view", "View exam results and grades"),

    # ============================================================
    # FINANCE MANAGEMENT
    # ============================================================
    ("fee:structure_manage", "Create and manage fee structures and categories"),
    ("fee:collection", "Collect fees and record payments"),
    ("fee:view", "View fee records and payment history"),
    ("fee:report", "Generate and view financial reports"),

    # ============================================================
    # COMMUNICATION & NOTIFICATIONS
    # ============================================================
    ("notification:student_level", "Send and manage notifications to students only"),
    ("notification:all_staff_level", "Send and manage notifications to all staff members (principals, teachers, other staff)"),
    ("notification:admin_level", "Send and manage system-wide admin notifications"),

    # ============================================================
    # CONTENT & LEARNING RESOURCES
    # ============================================================
    
    ("content:full_management", "Manage learning content including study materials, PDFs, videos, and images (full CRUD)"),
    ("content:basic_management", "Manage learning content including study materials, PDFs, videos, and images (only create)"),

    # ============================================================
    # ADVANCED FEATURES
    # ============================================================
    ("voice_agent:ai_voice_agent_manage", "Manage AI voice agent features and configurations"),
    ("report:master", "Access admin-level master reports with complete school analytics"),
    ("report:basic", "Access staff-level basic reports"),
    ("recycle_bin:user", "Manage user recycle bin (restore or permanently delete)"),
]
DEFAULT_PERMISSIONS_PRINCIPAL = [
    # ============================================================
    # SYSTEM ADMINISTRATION
    # ============================================================
    # ("system:settings", "Manage system-wide settings and configurations"),
    # ("user:role_manage", "Create, update, and delete user roles"),
    # ("permission:manage", "Assign and revoke permissions"),
    ("bulk:entry", "Perform bulk operations (import/export data)"),

    # ============================================================
    # STUDENT MANAGEMENT
    # ============================================================
    ("student:create", "Create new student records"),
    ("student:update", "Update existing student information"),
    ("student:delete", "Delete student records"),
    ("student:view", "View individual student details"),
    ("student:view_all", "View all students across all classes"),
    ("student:view_class", "View students within specific class only"),
    ("student:status_change", "Change student status (active/inactive/transferred)"),

    # ============================================================
    # STAFF MANAGEMENT
    # ============================================================
    ("staff:create", "Create new staff member records"),
    ("staff:update", "Update existing staff member information"),
    ("staff:delete", "Delete staff member records"),
    ("staff:view", "View individual staff member details"),
    ("staff:view_all", "View all staff members"),

    # ============================================================
    # CLASS MANAGEMENT
    # ============================================================
    ("class:management", "Full class management including CRUD operations, class schedules, and assignments"),

    # ============================================================
    # ATTENDANCE MANAGEMENT
    # ============================================================
    ("attendance:student_attendance_management", "Manage student attendance including marking, updating, and viewing attendance reports"),
    # ("attendance:staff_attendance_management", "Manage staff attendance including marking, updating, and viewing attendance reports"),

    # ============================================================
    # EXAM & RESULT MANAGEMENT
    # ============================================================
    ("exam:full_management", "Manage exams including creating, scheduling, and editing (excludes grading and result publishing)"),
    ("grade:assign", "Assign and update grades for exams"),
    ("result:publish", "Publish exam results to students and parents"),
    ("result:view", "View exam results and grades"),

    # ============================================================
    # FINANCE MANAGEMENT
    # ============================================================
    ("fee:structure_manage", "Create and manage fee structures and categories"),
    ("fee:collection", "Collect fees and record payments"),
    ("fee:view", "View fee records and payment history"),
    ("fee:report", "Generate and view financial reports"),

    # ============================================================
    # COMMUNICATION & NOTIFICATIONS
    # ============================================================
    ("notification:student_level", "Send and manage notifications to students only"),
    ("notification:all_staff_level", "Send and manage notifications to all staff members (principals, teachers, other staff)"),
    # ("notification:admin_level", "Send and manage system-wide admin notifications"),

    # ============================================================
    # CONTENT & LEARNING RESOURCES
    # ============================================================
    
    ("content:full_management", "Manage learning content including study materials, PDFs, videos, and images (full CRUD)"),
    ("content:basic_management", "Manage learning content including study materials, PDFs, videos, and images (only create)"),

    # ============================================================
    # ADVANCED FEATURES
    # ============================================================
    # ("voice_agent:ai_voice_agent_manage", "Manage AI voice agent features and configurations"),
    # ("report:master", "Access admin-level master reports with complete school analytics"),
    ("report:basic", "Access staff-level basic reports"),
    ("recycle_bin:user", "Manage user recycle bin (restore or permanently delete)"),
]
DEFAULT_PERMISSIONS_TEACHER = [
    # ============================================================
    # SYSTEM ADMINISTRATION
    # ============================================================
    # ("system:settings", "Manage system-wide settings and configurations"),
    # ("user:role_manage", "Create, update, and delete user roles"),
    # ("permission:manage", "Assign and revoke permissions"),
    # ("bulk:entry", "Perform bulk operations (import/export data)"),

    # ============================================================
    # STUDENT MANAGEMENT
    # ============================================================
    ("student:create", "Create new student records"),
    ("student:update", "Update existing student information"),
    # ("student:delete", "Delete student records"),
    ("student:view", "View individual student details"),
    # ("student:view_all", "View all students across all classes"),
    ("student:view_class", "View students within specific class only"),
    # ("student:status_change", "Change student status (active/inactive/transferred)"),

    # ============================================================
    # STAFF MANAGEMENT
    # ============================================================
    # ("staff:create", "Create new staff member records"),
    # ("staff:update", "Update existing staff member information"),
    # ("staff:delete", "Delete staff member records"),
    # ("staff:view", "View individual staff member details"),
    # ("staff:view_all", "View all staff members"),

    # ============================================================
    # CLASS MANAGEMENT
    # ============================================================
    # ("class:management", "Full class management including CRUD operations, class schedules, and assignments"),

    # ============================================================
    # ATTENDANCE MANAGEMENT
    # ============================================================
    ("attendance:student_attendance_management", "Manage student attendance including marking, updating, and viewing attendance reports"),
    # ("attendance:staff_attendance_management", "Manage staff attendance including marking, updating, and viewing attendance reports"),

    # ============================================================
    # EXAM & RESULT MANAGEMENT
    # ============================================================
    # ("exam:full_management", "Manage exams including creating, scheduling, and editing (excludes grading and result publishing)"),
    ("grade:assign", "Assign and update grades for exams"),
    # ("result:publish", "Publish exam results to students and parents"),
    ("result:view", "View exam results and grades"),

    # ============================================================
    # FINANCE MANAGEMENT
    # ============================================================
    # ("fee:structure_manage", "Create and manage fee structures and categories"),
    # ("fee:collection", "Collect fees and record payments"),
    ("fee:view", "View fee records and payment history"),
    # ("fee:report", "Generate and view financial reports"),

    # ============================================================
    # COMMUNICATION & NOTIFICATIONS
    # ============================================================
    ("notification:student_level", "Send and manage notifications to students only"),
    # ("notification:all_staff_level", "Send and manage notifications to all staff members (principals, teachers, other staff)"),
    # ("notification:admin_level", "Send and manage system-wide admin notifications"),

    # ============================================================
    # CONTENT & LEARNING RESOURCES
    # ============================================================
    
    # ("content:full_management", "Manage learning content including study materials, PDFs, videos, and images (full CRUD)"),
    ("content:basic_management", "Manage learning content including study materials, PDFs, videos, and images (only create)"),

    # ============================================================
    # ADVANCED FEATURES
    # ============================================================
    # ("voice_agent:ai_voice_agent_manage", "Manage AI voice agent features and configurations"),
    # ("report:master", "Access admin-level master reports with complete school analytics"),
    ("report:basic", "Access staff-level basic reports"),
    # ("recycle_bin:user", "Manage user recycle bin (restore or permanently delete)"),
]
DEFAULT_PERMISSIONS_OTHER_STAFF = [
#    0
]