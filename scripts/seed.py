import asyncio
import hashlib
import os
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Employee,
    EmployeeSiteAssignment,
    Organization,
    Site,
    SupervisorSiteAssignment,
    User,
)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$" + salt.hex() + "$" + digest.hex()


async def seed() -> None:
    if settings.app_env.lower() not in {"development", "dev", "local", "test"}:
        raise RuntimeError(
            "Refusing to seed a non-development environment. "
            "Set APP_ENV=development for local seeding."
        )

    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@demo.local").lower()
    admin_password = os.getenv("SEED_ADMIN_PASSWORD", "Admin@12345")
    supervisor_email = os.getenv("SEED_SUPERVISOR_EMAIL", "supervisor@demo.local").lower()
    supervisor_password = os.getenv("SEED_SUPERVISOR_PASSWORD", "Supervisor@12345")
    qr_token = os.getenv("SEED_SITE_QR_TOKEN", "DEMO-SITE-QR-2026")

    async with SessionLocal() as db:
        organization = (
            await db.execute(
                select(Organization).where(Organization.name == "Demo Workforce")
            )
        ).scalar_one_or_none()

        if organization is None:
            organization = Organization(name="Demo Workforce", active=True)
            db.add(organization)
            await db.flush()

        admin = (
            await db.execute(select(User).where(User.email == admin_email))
        ).scalar_one_or_none()
        if admin is None:
            admin = User(
                organization_id=organization.id,
                email=admin_email,
                password_hash=hash_password(admin_password),
                role="ADMIN",
                active=True,
            )
            db.add(admin)

        supervisor = (
            await db.execute(select(User).where(User.email == supervisor_email))
        ).scalar_one_or_none()
        if supervisor is None:
            supervisor = User(
                organization_id=organization.id,
                email=supervisor_email,
                password_hash=hash_password(supervisor_password),
                role="SUPERVISOR",
                active=True,
            )
            db.add(supervisor)

        await db.flush()

        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization.id,
                    Employee.employee_code == "EMP001",
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            employee = Employee(
                organization_id=organization.id,
                employee_code="EMP001",
                full_name="Demo Employee",
                email="employee@demo.local",
                salary=30000,
                active=True,
            )
            db.add(employee)

        site = (
            await db.execute(
                select(Site).where(
                    Site.organization_id == organization.id,
                    Site.name == "Demo Site",
                )
            )
        ).scalar_one_or_none()
        if site is None:
            site = Site(
                organization_id=organization.id,
                name="Demo Site",
                qr_token_hash=hashlib.sha256(qr_token.encode()).hexdigest(),
                active=True,
            )
            db.add(site)
        else:
            site.qr_token_hash = hashlib.sha256(qr_token.encode()).hexdigest()
            site.active = True

        await db.flush()

        employee_assignment = (
            await db.execute(
                select(EmployeeSiteAssignment).where(
                    EmployeeSiteAssignment.employee_id == employee.id,
                    EmployeeSiteAssignment.site_id == site.id,
                )
            )
        ).scalar_one_or_none()
        if employee_assignment is None:
            db.add(
                EmployeeSiteAssignment(
                    employee_id=employee.id,
                    site_id=site.id,
                    active=True,
                )
            )
        else:
            employee_assignment.active = True

        supervisor_assignment = (
            await db.execute(
                select(SupervisorSiteAssignment).where(
                    SupervisorSiteAssignment.user_id == supervisor.id,
                    SupervisorSiteAssignment.site_id == site.id,
                )
            )
        ).scalar_one_or_none()
        if supervisor_assignment is None:
            db.add(
                SupervisorSiteAssignment(
                    user_id=supervisor.id,
                    site_id=site.id,
                    active=True,
                )
            )
        else:
            supervisor_assignment.active = True

        await db.commit()

        print("\nDevelopment seed completed.")
        print(f"Organization ID : {organization.id}")
        print(f"Admin email     : {admin_email}")
        print(f"Admin password  : {admin_password}")
        print(f"Supervisor email: {supervisor_email}")
        print(f"Supervisor pass : {supervisor_password}")
        print(f"Employee ID     : {employee.id}")
        print(f"Employee code   : {employee.employee_code}")
        print(f"Site ID         : {site.id}")
        print(f"QR token        : {qr_token}")
        print("\nUse the supervisor account for QR attendance tests.")


if __name__ == "__main__":
    asyncio.run(seed())
