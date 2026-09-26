from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, org_allowed
from app.db.session import get_db
from app.models import Employee as EmployeeModel, User
from app.schemas.employee import Employee

router = APIRouter()

@router.get("", response_model=list[Employee])
async def list_employees(organization_id: Optional[int] = Query(None), active: Optional[bool] = Query(True), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if organization_id is not None and not org_allowed(user, organization_id):
        raise HTTPException(status_code=403, detail="Not permitted")
    stmt = select(EmployeeModel)
    org_id = organization_id if user.role == "SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None:
        stmt = stmt.where(EmployeeModel.organization_id == org_id)
    if active is not None:
        stmt = stmt.where(EmployeeModel.active == active)
    result = await db.execute(stmt.order_by(EmployeeModel.full_name))
    return [Employee(id=e.id, organization_id=e.organization_id, employee_code=e.employee_code, full_name=e.full_name, email=e.email, active=e.active, salary=float(e.salary)) for e in result.scalars()]

@router.get("/{employee_id}", response_model=Employee)
async def get_employee(employee_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    employee = await db.get(EmployeeModel, employee_id)
    if not employee or not org_allowed(user, employee.organization_id):
        raise HTTPException(status_code=404, detail="Employee not found")
    return Employee(id=employee.id, organization_id=employee.organization_id, employee_code=employee.employee_code, full_name=employee.full_name, email=employee.email, active=employee.active, salary=float(employee.salary))
