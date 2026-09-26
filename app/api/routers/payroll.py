from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, org_allowed
from app.db.session import get_db
from app.models import Attendance, Employee as EmployeeModel, PayrollItem, PayrollRun as PayrollRunModel, SalarySlip, User
from app.schemas.payroll import PayrollItemResponse, PayrollRun, PayrollRunRequest

router = APIRouter()

def _working_days(year: int, month: int) -> int:
    return sum(1 for d in range(1, monthrange(year, month)[1] + 1) if date(year, month, d).weekday() < 5)

def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _item_response(item: PayrollItem) -> PayrollItemResponse:
    return PayrollItemResponse(employee_id=item.employee_id, gross_salary=float(item.gross_salary), deduction_amount=float(item.deduction_amount), overtime_amount=float(item.overtime_amount), final_payable=float(item.final_payable))

async def _payroll_response(run: PayrollRunModel, db: AsyncSession) -> PayrollRun:
    result = await db.execute(select(PayrollItem).where(PayrollItem.payroll_run_id == run.id).order_by(PayrollItem.employee_id))
    return PayrollRun(id=run.id, organization_id=run.organization_id, year=run.year, month=run.month, status=run.status, items=[_item_response(i) for i in result.scalars()])

@router.get("/runs", response_model=list[PayrollRun])
async def list_payroll_runs(organization_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if organization_id is not None and not org_allowed(user, organization_id): raise HTTPException(status_code=403, detail="Not permitted")
    org_id = organization_id if user.role == "SUPER_ADMIN" and organization_id else user.organization_id
    stmt = select(PayrollRunModel)
    if org_id is not None: stmt = stmt.where(PayrollRunModel.organization_id == org_id)
    result = await db.execute(stmt.order_by(PayrollRunModel.year.desc(), PayrollRunModel.month.desc()))
    return [await _payroll_response(r, db) for r in result.scalars()]

@router.post("/runs", response_model=PayrollRun)
async def create_payroll_run(payload: PayrollRunRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not org_allowed(user, payload.organization_id): raise HTTPException(status_code=403, detail="Not permitted")
    existing = await db.execute(select(PayrollRunModel).where(PayrollRunModel.organization_id == payload.organization_id, PayrollRunModel.year == payload.year, PayrollRunModel.month == payload.month))
    if existing.scalar_one_or_none(): raise HTTPException(status_code=409, detail="Payroll run already exists for this period")
    run = PayrollRunModel(organization_id=payload.organization_id, year=payload.year, month=payload.month, created_by=user.id, status="DRAFT")
    db.add(run); await db.commit(); await db.refresh(run)
    return await _payroll_response(run, db)

@router.get("/runs/{payroll_run_id}", response_model=PayrollRun)
async def get_payroll_run(payroll_run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await db.get(PayrollRunModel, payroll_run_id)
    if not run or not org_allowed(user, run.organization_id): raise HTTPException(status_code=404, detail="Payroll run not found")
    return await _payroll_response(run, db)

@router.post("/runs/{payroll_run_id}/finalize", response_model=PayrollRun)
async def finalize_payroll_run(payroll_run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await db.get(PayrollRunModel, payroll_run_id)
    if not run or not org_allowed(user, run.organization_id): raise HTTPException(status_code=404, detail="Payroll run not found")
    if run.status == "FINALIZED": return await _payroll_response(run, db)
    if run.status != "DRAFT": raise HTTPException(status_code=409, detail="Payroll run is not editable")
    employees_result = await db.execute(select(EmployeeModel).where(EmployeeModel.organization_id == run.organization_id, EmployeeModel.active.is_(True)))
    divisor = Decimal(_working_days(run.year, run.month) or 1)
    start = date(run.year, run.month, 1); end = date(run.year, run.month, monthrange(run.year, run.month)[1])
    for employee in employees_result.scalars():
        att_result = await db.execute(select(Attendance).where(Attendance.employee_id == employee.id, Attendance.work_date >= start, Attendance.work_date <= end, Attendance.approval_status == "APPROVED"))
        present = Decimal("0"); leave = Decimal("0"); overtime_minutes = 0
        for attendance in att_result.scalars():
            if attendance.status == "HALF_DAY": present += Decimal("0.5")
            elif attendance.status in {"PRESENT", "HOLIDAY"}: present += Decimal("1")
            elif attendance.status == "LEAVE": leave += Decimal("1")
            overtime_minutes += attendance.overtime_minutes
        gross = Decimal(str(employee.salary)); daily = gross / divisor
        deduction = _money(daily * max(Decimal("0"), divisor - present - leave))
        overtime = _money((daily / Decimal("8")) * Decimal(overtime_minutes) / Decimal("60"))
        item = PayrollItem(payroll_run_id=run.id, employee_id=employee.id, gross_salary=gross, deduction_amount=deduction, overtime_amount=overtime, final_payable=_money(gross - deduction + overtime), present_days=present, leave_days=leave, overtime_minutes=overtime_minutes)
        db.add(item); await db.flush()
        db.add(SalarySlip(payroll_item_id=item.id, employee_id=employee.id, year=run.year, month=run.month, slip_number=f"SLIP-{run.year}{run.month:02d}-{employee.employee_code}", generated_at=datetime.now(timezone.utc)))
    run.status = "FINALIZED"; run.finalized_at = datetime.now(timezone.utc)
    await db.commit(); await db.refresh(run)
    return await _payroll_response(run, db)

@router.get("/employees/{employee_id}/salary-slips/{year}/{month}")
async def get_salary_slip(employee_id: int, year: int, month: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    employee = await db.get(EmployeeModel, employee_id)
    if not employee or not org_allowed(user, employee.organization_id): raise HTTPException(status_code=404, detail="Salary slip not found")
    result = await db.execute(select(SalarySlip, PayrollItem, PayrollRunModel).join(PayrollItem, PayrollItem.id == SalarySlip.payroll_item_id).join(PayrollRunModel, PayrollRunModel.id == PayrollItem.payroll_run_id).where(SalarySlip.employee_id == employee_id, SalarySlip.year == year, SalarySlip.month == month, PayrollRunModel.status == "FINALIZED"))
    row = result.first()
    if not row: raise HTTPException(status_code=404, detail="Salary slip not found")
    slip, item, _ = row
    buffer = io.BytesIO(); pdf = canvas.Canvas(buffer, pagesize=A4); pdf.setTitle(slip.slip_number)
    pdf.setFont("Helvetica-Bold", 16); pdf.drawString(50, 800, "Salary Slip")
    lines = [("Slip Number", slip.slip_number), ("Employee", employee.full_name), ("Employee Code", employee.employee_code), ("Period", f"{month:02d}/{year}"), ("Gross Salary", f"INR {float(item.gross_salary):,.2f}"), ("Deductions", f"INR {float(item.deduction_amount):,.2f}"), ("Overtime", f"INR {float(item.overtime_amount):,.2f}"), ("Final Payable", f"INR {float(item.final_payable):,.2f}")]
    y = 760; pdf.setFont("Helvetica", 10)
    for label, value in lines:
        pdf.drawString(60, y, f"{label}:"); pdf.drawRightString(520, y, value); y -= 28
    pdf.save(); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{slip.slip_number}.pdf"'})
