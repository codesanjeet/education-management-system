# Base
from .base import Base

# Institution
from .institution_model import InstitutionDB, InstitutionUsageDB,InstitutionInfoDB,ClassroomDB,ExamSeatingDB

# Super Admin
from .super_admin_model import SuperAdminDB, SuperAdminLogDB, SuperAdminSecurityDB

# Users
from .user_model import UserDB, UserLogDB, UserSecurityDB

# Role-specific models
from .role_specific.student_model import (
    StudentDB,
    StudentAttendanceDB,
    StudentFeesDB,
    StudentGradeDB,
    DisciplinaryRecordDB
)
from .fee_model import *
from .role_specific.admin_model import AdminDB

from .role_specific.principal_model import PrincipalDB

from .role_specific.teacher_model import TeacherDB

from .role_specific.other_staff_model import OtherStaffDB

from .role_specific.staff_sub_models import StaffAttendanceDB, StaffSalaryDB

# Classes
from .classes_model import ClassDB, ClassScheduleDB,StudyMaterialDB
from .ai_agent_model import AIAgentDB, KnowledgeBaseDB, AIUnansweredQuestionDB,AIConversationDB,AIChannelSessionDB

from .attendance_model import ClassAttendanceAggDB,DaysClassAttendanceAggDB,StaffAttendanceAggDB,StudentAttendanceAggDB,InstitutionAttendanceAggDB,DaysInstitutionAttendanceAggDB,DaysStaffAttendanceAggDB

from .permission_model import PermissionDB,UserPermissionDB
from .admission_model import InstitutionPageDB, AdmissionFormDB
from .notification_model import NotificationsDB, NotificationReadDB,WhatsAppConfigDB,EmailConfigDB,SmsConfigDB,AutomationRuleDB,MessageLogDB    

# define __all__ for clarity
__all__ = [
    "Base",
    "InstitutionDB",
    "SuperAdminDB", "SuperAdminLogDB", "SuperAdminSecurityDB",
    "UserDB", "UserLogDB", "UserSecurityDB",
    "StudentDB", "StudentAttendanceDB", "StudentFeesDB", "StudentGradeDB", "DisciplinaryRecordDB",
    "AdminDB",
    "PrincipalDB",
    "TeacherDB",
    "OtherStaffDB",
    "StaffAttendanceDB", "StaffSalaryDB",
    "ClassDB", "ClassScheduleDB","StudyMaterial"
]
