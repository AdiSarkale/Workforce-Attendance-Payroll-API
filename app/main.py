from datetime import date, datetime
from enum import Enum
from typing import Optional
import hashlib
import hmac
import os
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import Employee as EmployeeModel, Site as SiteModel, User

app = FastAPI(title=settings.app_name, version="0.2.0", description="Workforce attendance, site management and payroll API.")
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
class PunchRequest(BaseModel):
    employee_id:int; site_id:int; occurred_at:datetime; qr_token:str=Field(min_length=1)
class AttendanceRecord(BaseModel):
    id:int; employee_id:int; site_id:int; work_date:date; punch_in:Optional[datetime]=None; punch_out:Optional[datetime]=None; worked_minutes:int=0; overtime_minutes:int=0; status:AttendanceStatus=AttendanceStatus.PRESENT; approval_status:ApprovalStatus=ApprovalStatus.PENDING
class PayrollRunRequest(BaseModel): organization_id:int; year:int=Field(ge=2020,le=2100); month:int=Field(ge=1,le=12)
class PayrollItem(BaseModel): employee_id:int; gross_salary:float; deduction_amount:float=0; overtime_amount:float=0; final_payable:float
class PayrollRun(BaseModel): id:int; organization_id:int; year:int; month:int; status:str="DRAFT"; items:list[PayrollItem]=[]

def _hash_password(password:str,salt:bytes|None=None)->str:
    salt=salt or os.urandom(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310_000)
    return f"pbkdf2_sha256$310000$\{salt.hex()}$\{digest.hex()}"

def _verify_password(password:str,encoded:str)->bool:
    try:
        algorithm,rounds,salt_hex,digest_hex=encoded.split("$")
        if algorithm!="pbkdf2_sha256": return False
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(rounds))
        return hmac.compare_digest(candidate.hex(),digest_hex)
    except (ValueError,TypeError): return False

async def get_current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer),db:AsyncSession=Depends(get_db))->User:
    if not credentials: raise HTTPException(401,"Authentication required")
    try:
        payload=jwt.decode(credentials.credentials,settings.jwt_secret_key,algorithms=[settings.jwt_algorithm])
        user_id=int(payload.get("sub"))
    except (JWTError,TypeError,ValueError):
        raise HTTPException(401,"Invalid or expired token")
    user=await db.get(User,user_id)
    if not user or not user.active: raise HTTPException(401,"User is inactive or not found")
    return user

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
    stmt=select(EmployeeModel)
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None: stmt=stmt.where(EmployeeModel.organization_id==org_id)
    if active is not None: stmt=stmt.where(EmployeeModel.active==active)
    result=await db.execute(stmt.order_by(EmployeeModel.full_name))
    return [Employee(id=e.id,organization_id=e.organization_id,employee_code=e.employee_code,full_name=e.full_name,email=e.email,active=e.active,salary=float(e.salary)) for e in result.scalars()]

@app.get("/api/v1/employees/{employee_id}",response_model=Employee,tags=["employees"])
async def get_employee(employee_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    e=await db.get(EmployeeModel,employee_id)
    if not e or (user.organization_id is not None and e.organization_id!=user.organization_id and user.role!="SUPER_ADMIN"): raise HTTPException(404,"Employee not found")
    return Employee(id=e.id,organization_id=e.organization_id,employee_code=e.employee_code,full_name=e.full_name,email=e.email,active=e.active,salary=float(e.salary))

@app.get("/api/v1/sites",response_model=list[Site],tags=["sites"])
async def list_sites(organization_id:Optional[int]=Query(None),db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    stmt=select(SiteModel)
    org_id=organization_id if user.role=="SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None: stmt=stmt.where(SiteModel.organization_id==org_id)
    result=await db.execute(stmt.order_by(SiteModel.name))
    return [Site(id=s.id,organization_id=s.organization_id,name=s.name,active=s.active) for s in result.scalars()]

@app.get("/api/v1/sites/{site_id}",response_model=Site,tags=["sites"])
async def get_site(site_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(get_current_user)):
    s=await db.get(SiteModel,site_id)
    if not s or (user.organization_id is not None and s.organization_id!=user.organization_id and user.role!="SUPER_ADMIN"): raise HTTPException(404,"Site not found")
    return Site(id=s.id,organization_id=s.organization_id,name=s.name,active=s.active)

@app.post("/api/v1/attendance/punch",response_model=AttendanceRecord,tags=["attendance"])
async def punch_attendance(payload:PunchRequest,user:User=Depends(get_current_user)): raise HTTPException(501,"Attendance persistence and QR validation are not implemented yet")
@app.get("/api/v1/attendance",response_model=list[AttendanceRecord],tags=["attendance"])
async def list_attendance(organization_id:Optional[int]=Query(None),employee_id:Optional[int]=Query(None),site_id:Optional[int]=Query(None),from_date:Optional[date]=Query(None),to_date:Optional[date]=Query(None),user:User=Depends(get_current_user)): return []
@app.post("/api/v1/attendance/{attendance_id}/approve",response_model=AttendanceRecord,tags=["attendance"])
async def approve_attendance(attendance_id:int,user:User=Depends(get_current_user)): raise HTTPException(501,"Attendance persistence is not implemented yet")
@app.post("/api/v1/attendance/{attendance_id}/reject",response_model=AttendanceRecord,tags=["attendance"])
async def reject_attendance(attendance_id:int,user:User=Depends(get_current_user)): raise HTTPException(501,"Attendance persistence is not implemented yet")
@app.get("/api/v1/attendance/missing-punch-outs",response_model=list[AttendanceRecord],tags=["attendance"])
async def missing_punch_outs(organization_id:Optional[int]=Query(None),user:User=Depends(get_current_user)): return []

@app.post("/api/v1/payroll/runs",response_model=PayrollRun,tags=["payroll"])
async def create_payroll_run(payload:PayrollRunRequest,user:User=Depends(get_current_user)):
    if user.organization_id is not None and payload.organization_id!=user.organization_id and user.role!="SUPER_ADMIN": raise HTTPException(403,"Not permitted")
    return PayrollRun(id=0,organization_id=payload.organization_id,year=payload.year,month=payload.month,status="DRAFT",items=[])
@app.get("/api/v1/payroll/runs",response_model=list[PayrollRun],tags=["payroll"])
async def list_payroll_runs(organization_id:Optional[int]=Query(None),user:User=Depends(get_current_user)): return []
@app.get("/api/v1/payroll/runs/{payroll_run_id}",response_model=PayrollRun,tags=["payroll"])
async def get_payroll_run(payroll_run_id:int,user:User=Depends(get_current_user)): raise HTTPException(404,"Payroll run not found")
@app.post("/api/v1/payroll/runs/{payroll_run_id}/finalize",response_model=PayrollRun,tags=["payroll"])
async def finalize_payroll_run(payroll_run_id:int,user:User=Depends(get_current_user)): raise HTTPException(501,"Payroll persistence is not implemented yet")
@app.get("/api/v1/payroll/employees/{employee_id}/salary-slips/{year}/{month}",tags=["payroll"])
async def get_salary_slip(employee_id:int,year:int,month:int,user:User=Depends(get_current_user)): raise HTTPException(404,"Salary slip not found")
