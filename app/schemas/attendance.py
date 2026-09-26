from datetime import date, datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    LEAVE = "LEAVE"
    HOLIDAY = "HOLIDAY"
    MISSING_PUNCH_OUT = "MISSING_PUNCH_OUT"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class PunchRequest(BaseModel):
    employee_id: int
    site_id: int
    occurred_at: datetime
    qr_token: str = Field(min_length=1)

class AttendanceRecord(BaseModel):
    id: int
    employee_id: int
    site_id: int
    work_date: date
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    worked_minutes: int = 0
    overtime_minutes: int = 0
    status: AttendanceStatus = AttendanceStatus.PRESENT
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
