from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, org_allowed
from app.db.session import get_db
from app.models import Site as SiteModel, User
from app.schemas.site import Site

router = APIRouter()

@router.get("", response_model=list[Site])
async def list_sites(organization_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if organization_id is not None and not org_allowed(user, organization_id):
        raise HTTPException(status_code=403, detail="Not permitted")
    stmt = select(SiteModel)
    org_id = organization_id if user.role == "SUPER_ADMIN" and organization_id else user.organization_id
    if org_id is not None:
        stmt = stmt.where(SiteModel.organization_id == org_id)
    result = await db.execute(stmt.order_by(SiteModel.name))
    return [Site(id=s.id, organization_id=s.organization_id, name=s.name, active=s.active) for s in result.scalars()]

@router.get("/{site_id}", response_model=Site)
async def get_site(site_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    site = await db.get(SiteModel, site_id)
    if not site or not org_allowed(user, site.organization_id):
        raise HTTPException(status_code=404, detail="Site not found")
    return Site(id=site.id, organization_id=site.organization_id, name=site.name, active=site.active)
