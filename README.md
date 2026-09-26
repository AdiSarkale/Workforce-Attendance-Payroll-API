# Workforce Attendance & Payroll API

FastAPI backend foundation for workforce attendance, leave, overtime and payroll.

## Scope
- Organizations/customers
- 450+ employees
- Multi-site employee assignments
- Supervisor site assignments
- QR attendance
- Attendance corrections and approvals
- Missing punch-out approval
- Daily salary and overtime
- Annual leave and paid holidays
- Monthly payroll and salary slips
- Audit trail

## Stack
FastAPI, Pydantic Settings, SQLAlchemy 2 async, PostgreSQL, Alembic, JWT boundary, Docker and Pytest.

## API
Use `/docs`, `/redoc`, `/openapi.json`, and `/health`.

Lovable should consume this OpenAPI contract; business rules stay server-side.
