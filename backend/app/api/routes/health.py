from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process liveness only; deliberately avoids database and external providers."""
    return {"status": "ok"}


@router.get("/health/ready", response_model=HealthResponse)
def readiness(db: Session = Depends(get_db)) -> HealthResponse | JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "degraded", "database": "unavailable"})
    return HealthResponse(status="ok", database="connected")


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse | JSONResponse:
    return readiness(db)
