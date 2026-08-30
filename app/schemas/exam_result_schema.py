from pydantic import BaseModel
from typing import Optional

class SeatPosition(BaseModel):
    row_index: int
    column_index: int
    seat_in_col: int

class StudentInfo(BaseModel):
    name: Optional[str] = None
    roll_number: Optional[str] = None

class SeatingResponse(BaseModel):
    id: int
    seat_number: int
    user_id: int
    classroom_id: int
    position: SeatPosition
    student: Optional[StudentInfo] = None
    
    class Config:
        from_attributes = True


class ClassRoomAndClassCodes(BaseModel):
    class_codes: list[str]
    class_room_id: list[int] 
 