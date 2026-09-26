from datetime import date, datetime
from enum import Enum
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="Workforce Attendance & Payroll API",
    version="0.1.0",
    description="Backend foundation for multi-customer workforce attendance, leave, overtime and payroll.",
)

class Direction(str, Enum):
    IN = "IN"
    OUT = "OUT"

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

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class Employee(BaseModel):
    id: int
    organization_id: int
    employee_code: str
    full_name: str
    email: Optional[str] = None
    active: bool = True

class Site(BaseModel):
    id: int
    organization_id: int
    name: str
    active: bool = True

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

class PayrollRunRequest(BaseModel):
    organization_id: int
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)

class PayrollItem(BaseModel):
    employee_id: int
    gross_salary: float
    deduction_amount: float = 0
    overtime_amount: float = 0
    final_payable: float

class PayrollRun(BaseModel):
    id: int
    organization_id: int
    year: int
    month: int
    status: str = "DRAFT"
    items: list[PayrollItem] = []

@app.get("/", tags=["system"])
async def root():
    return {"service": app.title, "version": app.version, "docs": "/docs", "openapi": "/openapi.json"}

@app.get("/health", tags=["system"])
async def health():
    return {"status": "healthy"}

@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(payload: LoginRequest):
    # Authentication implementation is intentionally a backend integration boundary.
    return TokenResponse(access_token="development-token")

@app.get("/api/v1/employees", response_model=list[Employee], tags=["employees"])
async def list_employees(
    organization_id: Optional[int] = Query(default=None),
    active: Optional[bool] = Query(default=True),
):
    return []

@app.get("/api/v1/employees/{employee_id}", response_model=Employee, tags=["employees"])
async def get_employee(employee_id: int):
    raise HTTPException(status_code=404, detail="Employee not found")

@app.get("/api/v1/sites", response_model=list[Site], tags=["sites"])
async def list_sites(organization_id: Optional[int] = Query(default=None)):
    return []

@app.get("/api/v1/sites/{site_id}", response_model=Site, tags=["sites"])
async def get_site(site_id: int):
    raise HTTPException(status_code=404, detail="Site not found")

@app.post("/api/v1/attendance/punch", response_model=AttendanceRecord, tags=["attendance"])
async def punch_attendance(payload: PunchRequest):
    # Direction, replay protection, QR validation and authorization belong on the server.
    raise HTTPException(status_code=501, detail="Attendance persistence is not implemented yet")

@app.get("/api/v1/attendance", response_model=list[AttendanceRecord], tags=["attendance"])
async def list_attendance(
    organization_id: Optional[int] = Query(default=None),
    employee_id: Optional[int] = Query(default=None),
    site_id: Optional[int] = Query(default=None),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
):
    return []

@app.post("/api/v1/attendance/{attendance_id}/approve", response_model=AttendanceRecord, tags=["attendance"])
async def approve_attendance(attendance_id: int):
    raise HTTPException(status_code=501, detail="Attendance persistence is not implemented yet")

@app.post("/api/v1/attendance/{attendance_id}/reject", response_model=AttendanceRecord, tags=["attendance"])
async def reject_attendance(attendance_id: int):
    raise HTTPException(status_code=501, detail="Attendance persistence is not implemented yet")

@app.get("/api/v1/attendance/missing-punch-outs", response_model=list[AttendanceRecord], tags=["attendance"])
async def missing_punch_outs(organization_id: Optional[int] = Query(default=None)):
    return []

@app.post("/api/v1/payroll/runs", response_model=PayrollRun, tags=["payroll"])
async def create_payroll_run(payload: PayrollRunRequest):
    return PayrollRun(
        id=0,
        organization_id=payload.organization_id,
        year=payload.year,
        month=payload.month,
        status="DRAFT",
        items=[],
    )

@app.get("/api/v1/payroll/runs", response_model=list[PayrollRun], tags=["payroll"])
async def list_payroll_runs(organization_id: Optional[int] = Query(default=None)):
    return []

@app.get("/api/v1/payroll/runs/{payroll_run_id}", response_model=PayrollRun, tags=["payroll"])
async def get_payroll_run(payroll_run_id: int):
    raise HTTPException(status_code=404, detail="Payroll run not found")

@app.post("/api/v1/payroll/runs/{payroll_run_id}/finalize", response_model=PayrollRun, tags=["payroll"])
async def finalize_payroll_run(payroll_run_id: int):
    raise HTTPException(status_code=501, detail="Payroll persistence is not implemented yet")

@app.get("/api/v1/payroll/employees/{employee_id}/salary-slips/{year}/{month}", tags=["payroll"])
async def get_salary_slip(employee_id: int, year: int, month: int):
    raise HTTPException(status_code=404, detail="Salary slip not found")
