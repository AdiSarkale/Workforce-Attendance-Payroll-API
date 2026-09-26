from pydantic import BaseModel, Field

class PayrollRunRequest(BaseModel):
    organization_id: int
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)

class PayrollItemResponse(BaseModel):
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
    items: list[PayrollItemResponse] = []
