import asyncio
import hashlib
import os
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import Organization, User

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2_sha256$310000$" + salt.hex() + "$" + digest.hex()

async def main():
    async with SessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.name == "Demo Organization"))).scalar_one_or_none()
        if not org:
            org = Organization(name="Demo Organization")
            db.add(org)
            await db.flush()
        user = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one_or_none()
        if not user:
            db.add(User(organization_id=org.id, email="admin@example.com", password_hash=hash_password("ChangeMe123!"), role="ADMIN"))
        await db.commit()
        print("Demo admin: admin@example.com / ChangeMe123!")

if __name__ == "__main__":
    asyncio.run(main())
