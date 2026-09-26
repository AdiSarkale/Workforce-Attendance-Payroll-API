from calendar import monthrange
from datetime import date, datetime, timezone
from enum import Enum
import hashlib, hmac, io, os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import Attendance, Employee as EmployeeModel, EmployeeSiteAssignment, PayrollItem, PayrollRun as PayrollRunModel, SalarySlip, Site as SiteModel, SupervisorSiteAssignment, User

app = FastAPI(title=settings.app_name, version="0.3.0", description="Workforce attendance, site management and payroll API.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)

class AttendanceStatus(str, Enum):
    PRESENT="PRESENT"; ABSENT="ABSENT"; HALF_DAY="HALF_DAY"; LEAVE="LEAVE"; HOLIDAY="HOLIDAY"; MISSING_PUNCH_OUT="MISSING_PUNCH_OUT"
class ApprovalStatus(str, Enum):
    PENDING="PENDING"; APPROVED="APPROVED"; REJECTED="REJECTED"
class LoginRequest(BaseModel): email: str; password: str
class TokenResponse(BaseModel): access_token: str; token_type: str="bearer"
class CurrentUser(BaseModel): id:int; email:str; role:str; organization_id:Optional[int]=None
class Employee(BaseModel):
    id:int; organization_id:int; employee_code:str; full_name:str; email:Optional[str]=None; active:bool=True; salary:float=0
class Site(BaseModel): id:int; organization_id:int; name:str; active:bool=True
class PunchRequest(BaseModel): employee_id:int; site_id:int; occurred_at:datetime; qr_token:str=Field(min_length=1)
class AttendanceRecord(BaseModel):
    id:int; employee_id:int; site_id:int; work_date:date; punch_in:Optional[datetime]=None; punch_out:Optional[datetime]=None
    worked_minutes:int=0; overtime_minutes:int=0; status:AttendanceStatus=AttendanceStatus.PRESENT; approval_status:ApprovalStatus=ApprovalStatus.PENDING
class PayrollRunRequest(BaseModel): organization_id:int; year:int=Field(ge=2020,le=2100); month:int=Field(ge=1,le=12)
class PayrollItemResponse(BaseModel):
    employee_id:int; gross_salary:float; deduction_amount:float=0; overtime_amount:float=0; final_payable:float
class PayrollRun(BaseModel):
    id:int; organization_id:int; year:int; month:int; status:str="DRAFT"; items:list[PayrollItemResponse]=[]

def _hash_password(password:str,salt:bytes|None=None)->str:
    salt=salt or os.urandom(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310_000)
    return "pbkdf2_sha256$310000$"+salt.hex()+"$"+digest.hex()

def _verify_password(password:str,encoded:str)->bool:
    try:
        algorithm,rounds,salt_hex,digest_hex=encoded.split("$")
        if algorithm!="pbkdf2_sha256": return False
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(rounds))
        return hmac.compare_digest(candidate.hex(),digest_hex)
    except (ValueError,TypeError): return False

def _org_allowed(user:User,organization_id:int)->bool:
    return user.role=="SUPER_ADMIN" or user.organization_id==organization_id

async def get_current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:AsyncSession=Depends(get_db))->User:
    if not credentials: raise HTTPException(401,"Authentication required")
    try:
        payload=jwt.decode(credentials.credentials,settings.jwt_secret_key,algorithms=[settings.jwt_algorithm])
        user_id=int(payload.get("sub"))
    except (JWTError,TypeError,ValueError): raise HTTPException(401,"Invalid or expired token")
    user=await db.get(User,user_id)
    if not user or not user.active: raise HTTPException(401,"User is inactive or not found")
    return user

def _attendance_response(a:Attendance)->AttendanceRecord:
    return AttendanceRecord(id=a.id,employee_id=a.employee_id,site_id=a.site_id,work_date=a.work_date,punch_in=a.punch_in,punch_out=a.punch_out,worked_minutes=a.worked_minutes,overtime_minutes=a.overtime_minutes,status=a.status,approval_status=a.approval_status)

async def _can_access_site(user:User,site_id:int,db:AsyncSession)->SiteModel:
    site=await db.get(SiteModel,site_id)
    if not site or not site.active: raise HTTPException(404,"Site not found")
    if not _org_allowed(user,site.organization_id): raise HTTPException(403,"Not permitted")
    if user.role=="SUPERVISOR":
        q=await db.execute(select(SupervisorSiteAssignment).where(SupervisorSiteAssignment.user_id==user.id,SupervisorSiteAssignment.site_id==site_id,SupervisorSiteAssignment.active.is_(True)))
        if not q.scalar_one_or_none(): raise HTTPException(403,"Supervisor is not assigned to this site")
    return site

@app.get("/",tags=["system"])
async def root(): return {"service":app.title,"version":app.version,"docs":"/docs","openapi":"/openapi.json"}
@app.get("/health",tags=["system"])
async def health(): return {"status":"healthy"}

@app.post("/api/v1/auth/login",response_model=TokenResponse,tags=["auth"])
async def login(payload:LoginRequest,db:AsyncSession=Depends(get_db)):
    result=await db.execute(select(User).where(User.email==payload.email.lower()))
    user=result.scalar_one_or_none()
    if not user or not user.active or not _verify_password(payload.password,user.password_hash): raise HTTPException(401,"Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id,user.role))

@app.get("/api/v1/auth/me",response_model=CurrentUser,tags=["auth"])
async def me(user:User=Depends(get_current_user)): return CurrentUser(id=user.id,email=user.email,role=user.role,organization_id=user.organization_id)

@app.get("/api/v1/employees",response_model=list[Employee],tags=["employees"])
async def list_employees(organization_id:Optional[int]=Query(None),active:Optional[bool]=Query(True),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if organization_id is not None and not _org_allowed(user,organization_id): raise HTTPException(403,"Not permitted")
    stmt=select(EmployeeModel)
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None: stmt=stmt.where(EmployeeModel.organization_id==org_id)
    if active is not None: stmt=stmt.where(EmployeeModel.active==active)
    result=await db.execute(stmt.order_by(EmployeeModel.full_name))
    return [Employee(id=e.id,organization_id=e.organization_id,employee_code=e.employee_code,full_name=e.full_name,email=e.email,active=e.active,salary=float(e.salary)) for e in result.scalars()]

@app.get("/api/v1/employees/{employee_id}",response_model=Employee,tags=["employees"])
async def get_employee(employee_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    e=await db.get(EmployeeModel,employee_id)
    if not e or not _org_allowed(user,e.organization_id): raise HTTPException(404,"Employee not found")
    return Employee(id=e.id,organization_id=e.organization_id,employee_code=e.employee_code,full_name=e.full_name,email=e.email,active=e.active,salary=float(e.salary))

@app.get("/api/v1/sites",response_model=list[Site],tags=["sites"])
async def list_sites(organization_id:Optional[int]=Query(None),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if organization_id is not None and not _org_allowed(user,organization_id): raise HTTPException(403,"Not permitted")
    stmt=select(SiteModel)
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None: stmt=stmt.where(SiteModel.organization_id==org_id)
    result=await db.execute(stmt.order_by(SiteModel.name))
    return [Site(id=s.id,organization_id=s.organization_id,name=s.name,active=s.active) for s in result.scalars()]

@app.get("/api/v1/sites/{site_id}",response_model=Site,tags=["sites"])
async def get_site(site_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    s=await db.get(SiteModel,site_id)
    if not s or not _org_allowed(user,s.organization_id): raise HTTPException(404,"Site not found")
    return Site(id=s.id,organization_id=s.organization_id,name=s.name,active=s.active)

@app.post("/api/v1/attendance/punch",response_model=AttendanceRecord,tags=["attendance"])
async def punch_attendance(payload:PunchRequest,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    site=await _can_access_site(user,payload.site_id,db)
    employee=await db.get(EmployeeModel,payload.employee_id)
    if not employee or not employee.active or not _org_allowed(user,employee.organization_id) or employee.organization_id!=site.organization_id: raise HTTPException(404,"Employee not found")
    token_hash=hashlib.sha256(payload.qr_token.encode()).hexdigest()
    if not hmac.compare_digest(token_hash,site.qr_token_hash): raise HTTPException(403,"Invalid site QR token")
    assignment=await db.execute(select(EmployeeSiteAssignment).where(EmployeeSiteAssignment.employee_id==employee.id,EmployeeSiteAssignment.site_id==site.id,EmployeeSiteAssignment.active.is_(True)))
    if not assignment.scalar_one_or_none(): raise HTTPException(403,"Employee is not assigned to this site")
    occurred=payload.occurred_at if payload.occurred_at.tzinfo else payload.occurred_at.replace(tzinfo=timezone.utc)
    work_date=occurred.date()
    result=await db.execute(select(Attendance).where(Attendance.employee_id==employee.id,Attendance.work_date==work_date))
    record=result.scalar_one_or_none()
    if record is None:
        record=Attendance(employee_id=employee.id,site_id=site.id,work_date=work_date,punch_in=occurred,status="PRESENT",approval_status="PENDING")
        db.add(record)
    elif record.punch_out is not None: raise HTTPException(409,"Attendance is already punched in and out for this date")
    elif record.punch_in is None: record.punch_in=occurred; record.site_id=site.id
    else:
        if occurred<=record.punch_in: raise HTTPException(400,"Punch-out must be after punch-in")
        record.punch_out=occurred
        record.worked_minutes=max(0,int((occurred-record.punch_in).total_seconds()//60))
        record.overtime_minutes=max(0,record.worked_minutes-480)
        record.status="PRESENT" if record.worked_minutes>=240 else "HALF_DAY"
    await db.commit(); await db.refresh(record)
    return _attendance_response(record)

@app.get("/api/v1/attendance",response_model=list[AttendanceRecord],tags=["attendance"])
async def list_attendance(organization_id:Optional[int]=Query(None),employee_id:Optional[int]=Query(None),site_id:Optional[int]=Query(None),from_date:Optional[date]=Query(None),to_date:Optional[date]=Query(None),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if organization_id is not None and not _org_allowed(user,organization_id): raise HTTPException(403,"Not permitted")
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    stmt=select(Attendance).join(EmployeeModel,EmployeeModel.id==Attendance.employee_id)
    if org_id is not None: stmt=stmt.where(EmployeeModel.organization_id==org_id)
    if employee_id is not None: stmt=stmt.where(Attendance.employee_id==employee_id)
    if site_id is not None: stmt=stmt.where(Attendance.site_id==site_id)
    if from_date is not None: stmt=stmt.where(Attendance.work_date>=from_date)
    if to_date is not None: stmt=stmt.where(Attendance.work_date<=to_date)
    result=await db.execute(stmt.order_by(Attendance.work_date.desc(),Attendance.id.desc()))
    return [_attendance_response(a) for a in result.scalars()]

async def _set_approval(attendance_id:int,approved:bool,user:User,db:AsyncSession):
    record=await db.get(Attendance,attendance_id)
    if not record: raise HTTPException(404,"Attendance not found")
    employee=await db.get(EmployeeModel,record.employee_id)
    if not employee or not _org_allowed(user,employee.organization_id): raise HTTPException(404,"Attendance not found")
    if user.role not in {"ADMIN","SUPER_ADMIN","SUPERVISOR"}: raise HTTPException(403,"Approval permission required")
    if user.role=="SUPERVISOR": await _can_access_site(user,record.site_id,db)
    record.approval_status="APPROVED" if approved else "REJECTED"; record.approved_by=user.id
    await db.commit(); await db.refresh(record)
    return _attendance_response(record)

@app.post("/api/v1/attendance/{attendance_id}/approve",response_model=AttendanceRecord,tags=["attendance"])
async def approve_attendance(attendance_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)): return await _set_approval(attendance_id,True,user,db)

@app.post("/api/v1/attendance/{attendance_id}/reject",response_model=AttendanceRecord,tags=["attendance"])
async def reject_attendance(attendance_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)): return await _set_approval(attendance_id,False,user,db)

@app.get("/api/v1/attendance/missing-punch-outs",response_model=list[AttendanceRecord],tags=["attendance"])
async def missing_punch_outs(organization_id:Optional[int]=Query(None),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if organization_id is not None and not _org_allowed(user,organization_id): raise HTTPException(403,"Not permitted")
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    stmt=select(Attendance).join(EmployeeModel,EmployeeModel.id==Attendance.employee_id).where(Attendance.punch_in.is_not(None),Attendance.punch_out.is_(None))
    if org_id is not None: stmt=stmt.where(EmployeeModel.organization_id==org_id)
    result=await db.execute(stmt.order_by(Attendance.work_date.desc()))
    return [_attendance_response(a) for a in result.scalars()]

def _working_days(year:int,month:int)->int:
    return sum(1 for d in range(1,monthrange(year,month)[1]+1) if date(year,month,d).weekday()<5)
def _money(v:Decimal)->Decimal: return v.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
def _item_response(i:PayrollItem)->PayrollItemResponse: return PayrollItemResponse(employee_id=i.employee_id,gross_salary=float(i.gross_salary),deduction_amount=float(i.deduction_amount),overtime_amount=float(i.overtime_amount),final_payable=float(i.final_payable))
async def _payroll_response(run:PayrollRunModel,db:AsyncSession)->PayrollRun:
    result=await db.execute(select(PayrollItem).where(PayrollItem.payroll_run_id==run.id).order_by(PayrollItem.employee_id))
    return PayrollRun(id=run.id,organization_id=run.organization_id,year=run.year,month=run.month,status=run.status,items=[_item_response(i) for i in result.scalars()])

@app.get("/api/v1/payroll/runs",response_model=list[PayrollRun],tags=["payroll"])
async def list_payroll_runs(organization_id:Optional[int]=Query(None),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if organization_id is not None and not _org_allowed(user,organization_id): raise HTTPException(403,"Not permitted")
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    stmt=select(PayrollRunModel)
    if org_id is not None: stmt=stmt.where(PayrollRunModel.organization_id==org_id)
    result=await db.execute(stmt.order_by(PayrollRunModel.year.desc(),PayrollRunModel.month.desc()))
    return [await _payroll_response(r,db) for r in result.scalars()]

@app.post("/api/v1/payroll/runs",response_model=PayrollRun,tags=["payroll"])
async def create_payroll_run(payload:PayrollRunRequest,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    if not _org_allowed(user,payload.organization_id): raise HTTPException(403,"Not permitted")
    existing=await db.execute(select(PayrollRunModel).where(PayrollRunModel.organization_id==payload.organization_id,PayrollRunModel.year==payload.year,PayrollRunModel.month==payload.month))
    if existing.scalar_one_or_none(): raise HTTPException(409,"Payroll run already exists for this period")
    run=PayrollRunModel(organization_id=payload.organization_id,year=payload.year,month=payload.month,created_by=user.id,status="DRAFT")
    db.add(run); await db.commit(); await db.refresh(run)
    return await _payroll_response(run,db)

@app.get("/api/v1/payroll/runs/{payroll_run_id}",response_model=PayrollRun,tags=["payroll"])
async def get_payroll_run(payroll_run_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    run=await db.get(PayrollRunModel,payroll_run_id)
    if not run or not _org_allowed(user,run.organization_id): raise HTTPException(404,"Payroll run not found")
    return await _payroll_response(run,db)

@app.post("/api/v1/payroll/runs/{payroll_run_id}/finalize",response_model=PayrollRun,tags=["payroll"])
async def finalize_payroll_run(payroll_run_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    run=await db.get(PayrollRunModel,payroll_run_id)
    if not run or not _org_allowed(user,run.organization_id): raise HTTPException(404,"Payroll run not found")
    if run.status=="FINALIZED": return await _payroll_response(run,db)
    if run.status!="DRAFT": raise HTTPException(409,"Payroll run is not editable")
    employees_result=await db.execute(select(EmployeeModel).where(EmployeeModel.organization_id==run.organization_id,EmployeeModel.active.is_(True)))
    divisor=Decimal(_working_days(run.year,run.month) or 1)
    start=date(run.year,run.month,1); end=date(run.year,run.month,monthrange(run.year,run.month)[1])
    for employee in employees_result.scalars():
        att_result=await db.execute(select(Attendance).where(Attendance.employee_id==employee.id,Attendance.work_date>=start,Attendance.work_date<=end,Attendance.approval_status=="APPROVED"))
        present=Decimal("0"); leave=Decimal("0"); overtime_minutes=0
        for a in att_result.scalars():
            if a.status=="HALF_DAY": present+=Decimal("0.5")
            elif a.status in {"PRESENT","HOLIDAY"}: present+=Decimal("1")
            elif a.status=="LEAVE": leave+=Decimal("1")
            overtime_minutes+=a.overtime_minutes
        gross=Decimal(str(employee.salary)); daily=gross/divisor
        deduction=_money(daily*max(Decimal("0"),divisor-present-leave))
        overtime=_money((daily/Decimal("8"))*Decimal(overtime_minutes)/Decimal("60"))
        item=PayrollItem(payroll_run_id=run.id,employee_id=employee.id,gross_salary=gross,deduction_amount=deduction,overtime_amount=overtime,final_payable=_money(gross-deduction+overtime),present_days=present,leave_days=leave,overtime_minutes=overtime_minutes)
        db.add(item); await db.flush()
        db.add(SalarySlip(payroll_item_id=item.id,employee_id=employee.id,year=run.year,month=run.month,slip_number=f"SLIP-{run.year}{run.month:02d}-{employee.employee_code}",generated_at=datetime.now(timezone.utc)))
    run.status="FINALIZED"; run.finalized_at=datetime.now(timezone.utc)
    await db.commit(); await db.refresh(run)
    return await _payroll_response(run,db)

@app.get("/api/v1/payroll/employees/{employee_id}/salary-slips/{year}/{month}",tags=["payroll"])
async def get_salary_slip(employee_id:int,year:int,month:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    employee=await db.get(EmployeeModel,employee_id)
    if not employee or not _org_allowed(user,employee.organization_id): raise HTTPException(404,"Salary slip not found")
    result=await db.execute(select(SalarySlip,PayrollItem,PayrollRunModel).join(PayrollItem,PayrollItem.id==SalarySlip.payroll_item_id).join(PayrollRunModel,PayrollRunModel.id==PayrollItem.payroll_run_id).where(SalarySlip.employee_id==employee_id,SalarySlip.year==year,SalarySlip.month==month,PayrollRunModel.status=="FINALIZED"))
    row=result.first()
    if not row: raise HTTPException(404,"Salary slip not found")
    slip,item,_=row
    buffer=io.BytesIO(); pdf=canvas.Canvas(buffer,pagesize=A4); pdf.setTitle(slip.slip_number)
    pdf.setFont("Helvetica-Bold",16); pdf.drawString(50,800,"Salary Slip")
    lines=[("Slip Number",slip.slip_number),("Employee",employee.full_name),("Employee Code",employee.employee_code),("Period",f"{month:02d}/{year}"),("Gross Salary",f"INR {float(item.gross_salary):,.2f}"),("Deductions",f"INR {float(item.deduction_amount):,.2f}"),("Overtime",f"INR {float(item.overtime_amount):,.2f}"),("Final Payable",f"INR {float(item.final_payable):,.2f}")]
    y=760; pdf.setFont("Helvetica",10)
    for label,value in lines: pdf.drawString(60,y,f"{label}:"); pdf.drawRightString(520,y,value); y-=28
    pdf.save(); buffer.seek(0)
    return StreamingResponse(buffer,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{slip.slip_number}.pdf"'})
