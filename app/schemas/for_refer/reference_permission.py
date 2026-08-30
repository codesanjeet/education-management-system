from ...core.database import AsyncSessionLocal
from sqlalchemy import select
import asyncio
from ...models.permission_model import PermissionDB
DEFAULT_PERMISSIONS = [
    # ============================================================
    # SYSTEM ADMINISTRATION
    # ============================================================
    ("system:settings", "Manage system-wide settings and configurations"),
    ("user:role_manage", "Create, update, and delete user roles"),
    ("permission:manage", "Assign and revoke permissions"),
    ("bulk:entry", "Perform bulk operations (import/export data)"),
    ("admission:management", "Manage admission-related tasks and processes"),

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
    ("fee:report", "Generate and view financial reports ,fee dashboard"),
    ("fee:management", "Manage all the things related to fees"),

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
    ("recent_activity_logs:view", "To see recent activity"),
    ("report:master", "Access admin-level master reports with complete school analytics"),
    ("report:basic", "Access staff-level basic reports"),
    ("discipline:management", "Manage student discipline and take actions"),
    
    ("recycle_bin:user", "Manage user recycle bin (restore or permanently delete)"),
]

DEFAULT_PERMISSIONS_STUDENT = [
    
]

async def commit_default_permissions():
    # We use a context manager to handle the session manually for a script
    async with AsyncSessionLocal() as db:
        try:
            for name, description in DEFAULT_PERMISSIONS:
                #  Check if permission already exists to avoid duplicates
                result = await db.execute(select(PermissionDB).where(PermissionDB.name == name))
                existing = result.scalar_one_or_none()

                if not existing:
                    new_permission = PermissionDB(
                        name=name, 
                        description=description
                    )
                    db.add(new_permission)
            
            await db.commit()
            print("Default permissions successfully checked/created")
            
        except Exception as e:
            await db.rollback()
            print(f"Error: {e}")

if __name__ == "__main__":
    # 3. Use asyncio.run to execute the async function
    asyncio.run(commit_default_permissions())



