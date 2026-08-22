from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin_doctors, auth, doctor_self, doctors, health
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(admin_doctors.router, prefix=settings.api_prefix)
app.include_router(doctors.router, prefix=settings.api_prefix)
app.include_router(doctor_self.router, prefix=settings.api_prefix)
