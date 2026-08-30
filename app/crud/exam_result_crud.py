import random
from collections import defaultdict
from sqlalchemy import select, delete, exists
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.institution_schema import CreateClassRoom, ClassRoomResponse, UpdateClassRoom
from ..models.institution_model import InstitutionDB, ClassroomDB, ExamSeatingDB
from ..models.user_model import UserDB
from ..models.role_specific.student_model import StudentDB
from ..models.classes_model import ClassDB
from ..schemas.exam_result_schema import SeatingResponse, SeatPosition, StudentInfo
from ..core.exceptions import InstitutionNotFoundError, DatabaseError
from typing import Dict,Any,List
import logging

logger = logging.getLogger(__name__)


# ==================== CLASSROOM CRUD ====================

async def create_class_room(
    tenant_id: str,
    class_data: CreateClassRoom,
    db: AsyncSession
):
    """Create a new classroom."""
    

    
    # Get institution ID
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one()
    
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")
    try:
        # Calculate capacity
        total_capacity = sum(
            col.seat_in_each_col * col.row
            for col in class_data.layout_config
        )
        
        # Create classroom
        class_room = ClassroomDB(
            institution_id=inst_id,
            layout_config=[col.model_dump() for col in class_data.layout_config],
            room_number=class_data.room_number,
            floor=class_data.floor,
            capacity=total_capacity,
        )
        
        db.add(class_room)
        await db.commit()
        await db.refresh(class_room)
        
        return class_room
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating classroom: {e}", exc_info=True)
        raise DatabaseError("Unable to create classroom")


async def get_class_room(
    tenant_id: str,
    db: AsyncSession
):
    """Get all classrooms for an institution."""
    
    # Get institution ID (optimized)
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one_or_none()
    
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")
    
    # Get classrooms
    class_room_query = await db.execute(
        select(ClassroomDB).where(ClassroomDB.institution_id == inst_id)
    )
    class_rooms = class_room_query.scalars().all()
    
    return [
        ClassRoomResponse.model_validate(class_room, from_attributes=True)
        for class_room in class_rooms
    ]


async def update_class_room(
    tenant_id: str,
    class_data: UpdateClassRoom,
    db: AsyncSession
):
    """Update classroom information."""
    
    # Get institution ID
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one_or_none()
    
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")
    
    # Get classroom
    class_room_result = await db.execute(
        select(ClassroomDB).where(
            ClassroomDB.id == class_data.id,
            ClassroomDB.institution_id == inst_id
        )
    )
    class_room = class_room_result.scalar_one_or_none()
    
    if not class_room:
        raise ValueError("Classroom not found")
    
    # Update fields
    update_data = class_data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(class_room, field, value)
    
    try:
        await db.commit()
        await db.refresh(class_room)
        return class_room
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating classroom: {e}", exc_info=True)
        raise DatabaseError("Unable to update classroom")


async def delete_class_room(
    tenant_id: str,
    class_room_id: int,
    db: AsyncSession
):

    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one_or_none()

    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")

    # Get classroom
    class_room = await db.get(ClassroomDB, class_room_id)

    if not class_room or class_room.institution_id != inst_id:
        raise ValueError("Classroom not found")

    try:
        # Delete seating FIRST
        await db.execute(
            delete(ExamSeatingDB).where(
                ExamSeatingDB.classroom_id == class_room_id
            )
        )

        # Delete classroom
        await db.delete(class_room)

        # Commit ONCE
        await db.commit()

        return {"message": "Classroom deleted successfully"}

    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting classroom: {e}", exc_info=True)
        raise DatabaseError("Unable to delete classroom")
# ==================== SEATING ARRANGEMENT ====================

# async def generate_seating_arrangement(
#     db: AsyncSession,
#     class_room_id: List,
#     class_codes: List,
#     tenant_id: str,
# ) -> Dict[str, Any]:
#     """Generate exam seating arrangement with smart distribution."""
    
#     # Validation
#     if not tenant_id:
#         raise ValueError("tenant_id is required")
    
#     # ── 1. Fetch Institution ──
#     inst_query = await db.execute(
#         select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
#     )
#     inst_id = inst_query.scalar_one_or_none()
    
#     if not inst_id:
#         raise InstitutionNotFoundError("Institution not found")
    
#     # ── 2. Fetch Classrooms ──
#     class_room_query = await db.execute(
#         select(ClassroomDB).where(ClassroomDB.institution_id == inst_id,ClassroomDB.id.in_(class_room_id))
#     )
#     class_room_list = class_room_query.scalars().all()
    
#     if not class_room_list:
#         raise ValueError("No classrooms found")
    
#     # ── 3. Delete Existing Seating ──
#     classroom_ids = [room.id for room in class_room_list]
#     await db.execute(
#         delete(ExamSeatingDB).where(
#             ExamSeatingDB.classroom_id.in_(classroom_ids)
#         )
#     )
#     await db.flush()
    
#     # ── 4. Fetch Students ──
#     student_query = (
#         select(
#             StudentDB.user_id,
#             StudentDB.roll_number,
#             StudentDB.class_code,
#             ClassDB.department,
#             ClassDB.class_or_year_or_name,
#             ClassDB.program,
#             ClassDB.id.label('class_id')
#         )
#         .join(UserDB, StudentDB.user_id == UserDB.id)
#         .join(ClassDB, StudentDB.class_code == ClassDB.class_code)
#         .where(UserDB.tenant_id == tenant_id)
#         .where(UserDB.role == "student")
#         .where(ClassDB.class_code.in_(class_codes))
#     )
    
#     result = await db.execute(student_query)
#     students = [dict(row._mapping) for row in result.all()] 
    
#     if not students:
#         raise ValueError("No students found")
    
#     logger.info(f"Found {len(students)} students for seating")
    
#     # ── 5. Group Students by Class & Sort ──
#     def make_group_key(s):
#         key = s["class_or_year_or_name"]
#         if s.get("department"):
#             key += f"|{s['department']}"
#         if s.get("program"):
#             key += f"|{s['program']}"
#         return key
    
#     students_by_group = defaultdict(list)
#     for s in students:
#         identifier = make_group_key(s)
#         students_by_group[identifier].append({
#             "user_id": s["user_id"],
#             "roll_number": s["roll_number"],
#             "class_code": s["class_code"],
#             "department": s.get("department"),
#             "program": s.get("program"),
#             "year_or_name": s["class_or_year_or_name"],
#             "class_id": s["class_id"],
#         })
    
#     # Handle numeric and string roll numbers
#     for group_students in students_by_group.values():
#         group_students.sort(key=lambda x: (
#             int(x['roll_number']) if isinstance(x['roll_number'], (int, str)) and str(x['roll_number']).isdigit() 
#             else float('inf')
#         ))
    
#     # ── 6. Interleave Students (Anti-Cheating) ──
#     grouping = list(students_by_group.keys())
#     random.shuffle(grouping)
    
#     class_queues = {}
#     for c in grouping:
#         ordered = list(students_by_group[c])
#         if random.choice([True, False]):
#             ordered = ordered[::-1]
#         class_queues[c] = ordered
    
#     interleaved_students = []
#     while any(class_queues.values()):
#         for c in grouping:
#             if class_queues[c]:
#                 interleaved_students.append(class_queues[c].pop(0))
    
#     # ── 7. Generate Seat Positions ──
#     all_seat_positions = []
    
#     for room in class_room_list:
#         for layout in room.layout_config:
#             rows = layout['row']
#             columns = layout['column']
#             seats_per_bench = layout['seat_in_each_col']
            
#             for row_idx in range(rows):
#                 for col_idx in range(columns):
#                     for seat_idx in range(seats_per_bench):
#                         all_seat_positions.append({
#                             'classroom_id': room.id,
#                             'row_index': row_idx,
#                             'column_index': col_idx,
#                             'seat_in_col': seat_idx,
#                         })
    
#     total_seats = len(all_seat_positions)
    
#     if len(interleaved_students) > total_seats:
#         raise ValueError(
#             f"Insufficient seats: {len(interleaved_students)} students, "
#             f"{total_seats} seats available"
#         )
    
#     # ── 8. Assign Students to Seats ──
#     seating_records = []
#     seat_number = 1001
    
#     for student, seat_pos in zip(interleaved_students, all_seat_positions):
#         seating_records.append(ExamSeatingDB(
#             classroom_id=seat_pos['classroom_id'],
#             user_id=student['user_id'],
#             row_index=seat_pos['row_index'],
#             column_index=seat_pos['column_index'],
#             seat_in_col=seat_pos['seat_in_col'],
#             seat_number=seat_number,
#         ))
#         seat_number += 1
    
#     # ── 9. Bulk Insert ──
#     try:
#         db.add_all(seating_records)
#         await db.commit()
#         logger.info(f"Seating arrangement saved: {len(seating_records)} assignments")
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"Error saving seating: {e}", exc_info=True)
#         raise DatabaseError("Unable to save seating arrangement")
    
#     # ── 10. Return Summary ──
#     return {
#         "total_students": len(students),
#         "total_seats_used": len(seating_records),
#         "total_available_seats": total_seats,
#         "total_gaps_left": total_seats - len(seating_records),
#         "classrooms_used": len(class_room_list),
#         "classes_processed": len(students_by_group),
#         "seat_number_range": f"1001 - {seat_number - 1}",
#         "message": "Seating arrangement completed successfully"
#     }

import heapq


async def generate_seating_arrangement(
    db: AsyncSession,
    class_room_id: List,
    class_codes: List,
    tenant_id: str,
) -> Dict[str, Any]:
    """Generate exam seating arrangement with smart distribution."""

    if not tenant_id:
        raise ValueError("tenant_id is required")

    # ── 1. Fetch Institution ──
    inst_query = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_query.scalar_one_or_none()
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")

    # ── 2. Fetch Classrooms ──
    class_room_query = await db.execute(
        select(ClassroomDB).where(
            ClassroomDB.institution_id == inst_id,
            ClassroomDB.id.in_(class_room_id)
        )
    )
    class_room_list = class_room_query.scalars().all()
    if not class_room_list:
        raise ValueError("No classrooms found")

    # ── 3. Delete Existing Seating ──
    classroom_ids = [room.id for room in class_room_list]
    await db.execute(
        delete(ExamSeatingDB).where(ExamSeatingDB.classroom_id.in_(classroom_ids))
    )
    await db.flush()

    # ── 4. Fetch Students ──
    student_query = (
        select(
            StudentDB.user_id,
            StudentDB.roll_number,
            StudentDB.class_code,
            ClassDB.department,
            ClassDB.class_or_year_or_name,
            ClassDB.program,
            ClassDB.id.label('class_id')
        )
        .join(UserDB, StudentDB.user_id == UserDB.id)
        .join(ClassDB, StudentDB.class_code == ClassDB.class_code)
        .where(UserDB.tenant_id == tenant_id)
        .where(UserDB.role == "student")
        .where(ClassDB.class_code.in_(class_codes))
    )
    result = await db.execute(student_query)
    students = [dict(row._mapping) for row in result.all()]
    if not students:
        raise ValueError("No students found")

    logger.info(f"Found {len(students)} students for seating")

    # ── 5. Group Students by Class & Sort by roll number ──
    def make_group_key(s):
        key = s["class_or_year_or_name"]
        if s.get("department"):
            key += f"|{s['department']}"
        if s.get("program"):
            key += f"|{s['program']}"
        return key

    students_by_group = defaultdict(list)
    for s in students:
        students_by_group[make_group_key(s)].append({
            "user_id": s["user_id"],
            "roll_number": s["roll_number"],
            "class_code": s["class_code"],
            "department": s.get("department"),
            "program": s.get("program"),
            "year_or_name": s["class_or_year_or_name"],
            "class_id": s["class_id"],
        })

    for group_students in students_by_group.values():
        group_students.sort(key=lambda x: (
            int(x['roll_number'])
            if str(x['roll_number']).isdigit()
            else float('inf')
        ))

    # ── 6. Build per-room seat position lists, respecting capacity ──
    # Each room has its own seat list. We will fill rooms in order,
    # but interleave students proportionally so no room is monopolised
    # by one class.

    rooms_seat_positions: List[List[Dict]] = []

    for room in class_room_list:
        room_seats = []
        for layout in room.layout_config:
            rows = layout['row']
            columns = layout['column']
            seats_per_bench = layout['seat_in_each_col']
            for row_idx in range(rows):
                for col_idx in range(columns):
                    for seat_idx in range(seats_per_bench):
                        room_seats.append({
                            'classroom_id': room.id,
                            'row_index': row_idx,
                            'column_index': col_idx,
                            'seat_in_col': seat_idx,
                        })
        # FIX: enforce the declared capacity — never exceed it
        declared_capacity = room.capacity
        if len(room_seats) > declared_capacity:
            room_seats = room_seats[:declared_capacity]
        rooms_seat_positions.append(room_seats)

    total_seats = sum(len(r) for r in rooms_seat_positions)

    if len(students) > total_seats:
        raise ValueError(
            f"Insufficient seats: {len(students)} students, "
            f"{total_seats} seats available across all rooms"
        )

    # ── 7. Proportional interleave across ALL rooms combined ──
    # Always pick next student from the class with the most remaining,
    # so large classes are spread evenly rather than bunched at the end.

    class_queues: Dict[str, List] = {}
    for group_key, group_list in students_by_group.items():
        ordered = list(group_list)
        if random.choice([True, False]):
            ordered = ordered[::-1]
        class_queues[group_key] = ordered

    # Max-heap: (-remaining_count, class_key)
    heap = [(-len(q), k) for k, q in class_queues.items() if q]
    heapq.heapify(heap)

    interleaved_students = []
    while heap:
        neg_count, key = heapq.heappop(heap)
        interleaved_students.append(class_queues[key].pop(0))
        if class_queues[key]:
            heapq.heappush(heap, (-len(class_queues[key]), key))

    # ── 8. Distribute interleaved students across rooms, room by room ──
    # Students fill room 1 to its capacity, then room 2, etc.
    # Because the list is already proportionally interleaved, each room
    # gets a fair cross-section of all classes automatically.

    seating_records = []
    seat_number = 1001
    student_idx = 0

    for room_seats in rooms_seat_positions:
        for seat_pos in room_seats:
            if student_idx >= len(interleaved_students):
                break  # no more students to assign
            student = interleaved_students[student_idx]
            seating_records.append(ExamSeatingDB(
                classroom_id=seat_pos['classroom_id'],
                user_id=student['user_id'],
                row_index=seat_pos['row_index'],
                column_index=seat_pos['column_index'],
                seat_in_col=seat_pos['seat_in_col'],
                seat_number=seat_number,
            ))
            seat_number += 1
            student_idx += 1

    # ── 9. Bulk Insert ──
    try:
        db.add_all(seating_records)
        await db.commit()
        logger.info(f"Seating arrangement saved: {len(seating_records)} assignments")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving seating: {e}", exc_info=True)
        raise DatabaseError("Unable to save seating arrangement")

    # ── 10. Return Summary ──
    return {
        "total_students": len(students),
        "total_seats_used": len(seating_records),
        "total_available_seats": total_seats,
        "total_gaps_left": total_seats - len(seating_records),
        "classrooms_used": len(class_room_list),
        "classes_processed": len(students_by_group),
        "seat_number_range": f"1001 - {seat_number - 1}",
        "message": "Seating arrangement completed successfully"
    }





async def get_seating_by_classroom(
    db: AsyncSession,
    classroom_id: int,
    tenant_id: str,
) -> list[SeatingResponse]:
    """Get seating arrangement for a classroom."""
    
    # Verify classroom ownership
    classroom_check = (
        select(ClassroomDB.id)
        .join(InstitutionDB, ClassroomDB.institution_id == InstitutionDB.id)
        .where(ClassroomDB.id == classroom_id)
        .where(InstitutionDB.tenant_id == tenant_id)
    )
    
    classroom_result = await db.execute(classroom_check)
    if not classroom_result.scalar_one_or_none():
        raise ValueError(f"Classroom {classroom_id} not found")
    
    # Get seating with student info
    query = (
        select(
            ExamSeatingDB,
            UserDB.first_name,
            UserDB.last_name,
            StudentDB.roll_number
        )
        .join(UserDB, UserDB.id == ExamSeatingDB.user_id)
        .join(StudentDB, StudentDB.user_id == UserDB.id)
        .where(ExamSeatingDB.classroom_id == classroom_id)
        .order_by(ExamSeatingDB.seat_number)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        SeatingResponse(
            id=row.ExamSeatingDB.id,
            seat_number=row.ExamSeatingDB.seat_number,
            user_id=row.ExamSeatingDB.user_id,
            classroom_id=row.ExamSeatingDB.classroom_id,
            position=SeatPosition(
                row_index=row.ExamSeatingDB.row_index,
                column_index=row.ExamSeatingDB.column_index,
                seat_in_col=row.ExamSeatingDB.seat_in_col
            ),
            student=StudentInfo(
                name=f"{row.first_name} {row.last_name}",
                roll_number=row.roll_number
            )
        )
        for row in rows
    ]