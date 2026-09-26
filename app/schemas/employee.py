from typing import Optional
from pydantic import BaseModel

class Employee(BaseModel):
    id: int
    organization_id: int
    employee_code: str
    full_name: str
    email: Optional[str] = None
    active: bool = True
    salary: float = 0
