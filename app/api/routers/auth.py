import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse

router = APIRouter()

def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not user.active or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id, user.role))

@router.get("/me", response_model=CurrentUser)
async def me(user: User = Depends(get_current_user)):
    return CurrentUser(id=user.id, email=user.email, role=user.role, organization_id=user.organization_id)
