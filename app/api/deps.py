import hashlib
import hmac
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import Site, SupervisorSiteAssignment, User

bearer = HTTPBearer(auto_error=False)

def org_allowed(user: User, organization_id: int) -> bool:
    return user.role == "SUPER_ADMIN" or user.organization_id == organization_id

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User is inactive or not found")
    return user

async def can_access_site(user: User, site_id: int, db: AsyncSession) -> Site:
    site = await db.get(Site, site_id)
    if not site or not site.active:
        raise HTTPException(status_code=404, detail="Site not found")
    if not org_allowed(user, site.organization_id):
        raise HTTPException(status_code=403, detail="Not permitted")
    if user.role == "SUPERVISOR":
        query = await db.execute(
            select(SupervisorSiteAssignment).where(
                SupervisorSiteAssignment.user_id == user.id,
                SupervisorSiteAssignment.site_id == site_id,
                SupervisorSiteAssignment.active.is_(True),
            )
        )
        if not query.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Supervisor is not assigned to this site")
    return site

def verify_qr_token(token: str, expected_hash: str) -> bool:
    candidate = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(candidate, expected_hash)
