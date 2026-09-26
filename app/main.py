from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.auth import router as auth_router
from app.api.routers.employees import router as employees_router
from app.api.routers.sites import router as sites_router
from app.api.routers.attendance import router as attendance_router
from app.api.routers.payroll import router as payroll_router
from app.core.config import settings
from app.core.errors import install_exception_handlers

app = FastAPI(title=settings.app_name, version="0.3.0", description="Workforce attendance, site management and payroll API.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
install_exception_handlers(app)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(employees_router, prefix="/api/v1/employees", tags=["employees"])
app.include_router(sites_router, prefix="/api/v1/sites", tags=["sites"])
app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["attendance"])
app.include_router(payroll_router, prefix="/api/v1/payroll", tags=["payroll"])

@app.get("/", tags=["system"])
async def root():
    return {"service": app.title, "version": app.version, "docs": "/docs", "openapi": "/openapi.json"}

@app.get("/health", tags=["system"])
async def health():
    return {"status": "healthy"}
