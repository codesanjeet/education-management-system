from sqlalchemy import Column, Integer, String, Text, Boolean, Date, ForeignKey, JSONB, DateTime
from datetime import datetime
from .base import Base
class ExamSchedule(Base):
    __tablename__ = "exam_schedules"
    
    # Primary identification
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Exam basic information
    exam_name = Column(String(100), nullable=False)  # "Mid Semester", "Final Exam", "Unit Test 1"

    
    # Exam dates and duration
    exam_start_date = Column(Date, nullable=False)
    exam_end_date = Column(Date, nullable=False)
    
    # Venue information
    venue = Column(String(100), nullable=True)  # Main exam hall

    
    # Exam photo/documentation requirements
    photo = Column(String(255), nullable=True)
    photo_specifications = Column(JSONB, nullable=True, default=dict)
    # Example: {
    #   "size": "passport_size",
    #   "background": "white",
    #   "recent_months": 6,
    #   "format": "jpeg/png",
    #   "max_file_size": "2MB"
    # }
    
    # Instructions and guidelines
    exam_instructions = Column(JSONB, nullable=True, default=list)
    # Example: [
    #   "Bring valid ID card and admit card",
    #   "No electronic devices allowed",
    #   "Use blue/black pen only",
    #   "Report 30 minutes before exam"
    # ]
    
    # Exam routine/schedule
    exam_routine = Column(JSONB, nullable=False, default=list)
    # Example: [
    #   {
    #     "date": "2024-12-15",
    #     "subject": "Mathematics",
    #     "subject_code": "MTH101",
    #     "department": "CSE", 
    #     "start_time": "09:00",
    #     "end_time": "12:00",
    #     "duration_minutes": 180,
    #     "venue": "Main Hall A",
    #     "invigilator": "Dr. Smith",
    #     "max_marks": 100,
    #     "exam_type": "theory"
    #   }
    # ]
    

    total_marks = Column(Integer, nullable=True)
    passing_marks = Column(Integer, nullable=True)
    
    
    # Seating arrangement
    seating_arrangement = Column(JSONB, nullable=True, default=dict)
    # Example: {
    #   "pattern": "alternate",
    #   "roll_number_wise": true,
    #   "room_wise_allocation": {
    #     "Hall A": {"start_roll": "CSE101A001", "end_roll": "CSE101A060"},
    #     "Hall B": {"start_roll": "CSE101A061", "end_roll": "CSE101A120"}
    #   }
    # }
    
    # Staff and supervision
    exam_coordinator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Status and administrative
    exam_status = Column(String(20), default="scheduled")  # scheduled, ongoing, completed, cancelled, postponed
    is_active = Column(Boolean, default=True)

    
    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    

    
    def __repr__(self):
        return f"<ExamSchedule(exam_name='{self.exam_name}', class_id={self.class_id}, status='{self.exam_status}')>"
    
    @property
    def is_upcoming(self):
        """Check if exam is upcoming"""
        return self.exam_start_date > datetime.date.today()
    
    @property
    def is_ongoing(self):
        """Check if exam is currently ongoing"""
        today = datetime.date.today()
        return self.exam_start_date <= today <= self.exam_end_date
    
    @property
    def days_until_exam(self):
        """Get number of days until exam starts"""
        if self.is_upcoming:
            return (self.exam_start_date - datetime.date.today()).days
        return 0
    
    def add_routine_entry(self, date, subject, subject_code, department, start_time, end_time, venue=None, **kwargs):
        """Add a new entry to exam routine"""
        if not self.exam_routine:
            self.exam_routine = []
        
        # Calculate duration
        start = datetime.datetime.strptime(start_time, "%H:%M")
        end = datetime.datetime.strptime(end_time, "%H:%M")
        duration = int((end - start).total_seconds() / 60)
        
        routine_entry = {
            "date": date,
            "subject": subject,
            "subject_code": subject_code,
            "department": department,
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration,
            "venue": venue,
            **kwargs
        }
        self.exam_routine.append(routine_entry)
    
    def get_routine_by_date(self, exam_date):
        """Get exam routine for a specific date"""
        if not self.exam_routine:
            return []
        return [entry for entry in self.exam_routine if entry.get("date") == exam_date]
    
    def update_exam_status(self, new_status):
        """Update exam status with validation"""
        valid_statuses = ["scheduled", "ongoing", "completed", "cancelled", "postponed"]
        if new_status in valid_statuses:
            self.exam_status = new_status
        else:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")

