import hashlib
import hmac
from datetime import date, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import can_access_site, get_current_user, org_allowed
from app.db.session import get_db
from app.models import Attendance, Employee as EmployeeModel, EmployeeSiteAssignment, User
from app.schemas.attendance import ApprovalStatus, AttendanceRecord, PunchRequest

router = APIRouter()

def _response(record: Attendance) -> AttendanceRecord:
    return AttendanceRecord(id=record.id, employee_id=record.employee_id, site_id=record.site_id, work_date=record.work_date, punch_in=record.punch_in, punch_out=record.punch_out, worked_minutes=record.worked_minutes, overtime_minutes=record.overtime_minutes, status=record.status, approval_status=record.approval_status)

@router.post("/punch", response_model=AttendanceRecord)
async def punch_attendance(payload: PunchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    site = await can_access_site(user, payload.site_id, db)
    employee = await db.get(EmployeeModel, payload.employee_id)
    if not employee or not employee.active or not org_allowed(user, employee.organization_id) or employee.organization_id != site.organization_id:
        raise HTTPException(status_code=404, detail="Employee not found")
    token_hash = hashlib.sha256(payload.qr_token.encode()).hexdigest()
    if not hmac.compare_digest(token_hash, site.qr_token_hash):
        raise HTTPException(status_code=403, detail="Invalid site QR token")
    assignment = await db.execute(select(EmployeeSiteAssignment).where(EmployeeSiteAssignment.employee_id == employee.id, EmployeeSiteAssignment.site_id == site.id, EmployeeSiteAssignment.active.is_(True)))
    if not assignment.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Employee is not assigned to this site")
    occurred = payload.occurred_at if payload.occurred_at.tzinfo else payload.occurred_at.replace(tzinfo=timezone.utc)
    work_date = occurred.date()
    result = await db.execute(select(Attendance).where(Attendance.employee_id == employee.id, Attendance.work_date == work_date))
    record = result.scalar_one_or_none()
    if record is None:
        record = Attendance(employee_id=employee.id, site_id=site.id, work_date=work_date, punch_in=occurred, status="PRESENT", approval_status="PENDING")
        db.add(record)
    elif record.punch_out is not None:
        raise HTTPException(status_code=409, detail="Attendance is already punched in and out for this date")
    elif record.punch_in is None:
        record.punch_in = occurred
        record.site_id = site.id
    else:
        if occurred <= record.punch_in:
            raise HTTPException(status_code=400, detail="Punch-out must be after punch-in")
        record.punch_out = occurred
        record.worked_minutes = max(0, int((occurred - record.punch_in).total_seconds() // 60))
        record.overtime_minutes = max(0, record.worked_minutes - 480)
        record.status = "PRESENT" if record.worked_minutes >= 240 else "HALF_DAY"
    await db.commit()
    await db.refresh(record)
    return _response(record)

@router.get("", response_model=list[AttendanceRecord])
async def list_attendance(organization_id: Optional[int] = Query(None), employee_id: Optional[int] = Query(None), site_id: Optional[int] = Query(None), from_date: Optional[date] = Query(None), to_date: Optional[date] = Query(None), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if organization_id is not None and not org_allowed(user, organization_id):
        raise HTTPException(status_code=403, detail="Not permitted")
    org_id = organization_id if user.role == "SUPER_ADMIN" and organization_id else user.organization_id
    stmt = select(Attendance).join(EmployeeModel, EmployeeModel.id == Attendance.employee_id)
    if org_id is not None: stmt = stmt.where(EmployeeModel.organization_id == org_id)
    if employee_id is not None: stmt = stmt.where(Attendance.employee_id == employee_id)
    if site_id is not None: stmt = stmt.where(Attendance.site_id == site_id)
    if from_date is not None: stmt = stmt.where(Attendance.work_date >= from_date)
    if to_date is not None: stmt = stmt.where(Attendance.work_date <= to_date)
    result = await db.execute(stmt.order_by(Attendance.work_date.desc(), Attendance.id.desc()))
    return [_response(a) for a in result.scalars()]

async def _set_approval(attendance_id: int, approved: bool, user: User, db: AsyncSession):
    record = await db.get(Attendance, attendance_id)
    if not record:
        raise HTTPException(status_code=404, detail="Attendance not found")
    employee = await db.get(EmployeeModel, record.employee_id)
    if not employee or not org_allowed(user, employee.organization_id):
        raise HTTPException(status_code=404, detail="Attendance not found")
    if user.role not in {"ADMIN", "SUPER_ADMIN", "SUPERVISOR"}:
        raise HTTPException(status_code=403, detail="Approval permission required")
    if user.role == "SUPERVISOR":
        await can_access_site(user, record.site_id, db)
    record.approval_status = ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value
    record.approved_by = user.id
    await db.commit()
    await db.refresh(record)
    return _response(record)

@router.post("/{attendance_id}/approve", response_model=AttendanceRecord)
async def approve_attendance(attendance_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _set_approval(attendance_id, True, user, db)

@router.post("/{attendance_id}/reject", response_model=AttendanceRecord)
async def reject_attendance(attendance_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _set_approval(attendance_id, False, user, db)

@router.get("/missing-punch-outs", response_model=list[AttendanceRecord])
async def missing_punch_outs(organization_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if organization_id is not None and not org_allowed(user, organization_id):
        raise HTTPException(status_code=403, detail="Not permitted")
    org_id = organization_id if user.role == "SUPER_ADMIN" and organization_id else user.organization_id
    stmt = select(Attendance).join(EmployeeModel, EmployeeModel.id == Attendance.employee_id).where(Attendance.punch_in.is_not(None), Attendance.punch_out.is_(None))
    if org_id is not None: stmt = stmt.where(EmployeeModel.organization_id == org_id)
    result = await db.execute(stmt.order_by(Attendance.work_date.desc()))
    return [_response(a) for a in result.scalars()]
