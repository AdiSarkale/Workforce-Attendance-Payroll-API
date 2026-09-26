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


## Development seed

After the Docker stack is running and migrations have completed:

```powershell
docker compose exec api python scripts/seed.py
```

The seed is development-only and is idempotent. It creates:

- Demo organization
- Admin user
- Supervisor user
- One employee with salary
- One site
- Employee-to-site assignment
- Supervisor-to-site assignment
- A known site QR token for attendance testing

Default development credentials:

- Admin: `admin@demo.local` / `Admin@12345`
- Supervisor: `supervisor@demo.local` / `Supervisor@12345`
- Employee: `EMP001`
- Site QR token: `DEMO-SITE-QR-2026`

Override seed credentials/tokens with `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, `SEED_SUPERVISOR_EMAIL`, `SEED_SUPERVISOR_PASSWORD`, and `SEED_SITE_QR_TOKEN`.

The script refuses to run when `APP_ENV` is not a development/local/test environment.
