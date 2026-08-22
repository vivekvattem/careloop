from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin_doctors,
    appointment_views,
    appointments,
    auth,
    doctor_self,
    doctors,
    health,
    visits,
)
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
app.include_router(appointments.router, prefix=settings.api_prefix)
app.include_router(appointment_views.doctor_router, prefix=settings.api_prefix)
app.include_router(appointment_views.admin_router, prefix=settings.api_prefix)
app.include_router(visits.patient_router, prefix=settings.api_prefix)
app.include_router(visits.doctor_router, prefix=settings.api_prefix)
