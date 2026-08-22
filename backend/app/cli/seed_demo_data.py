import os
from dataclasses import dataclass
from datetime import date, time, timedelta

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories.user import UserRepository
from app.schemas.doctor import DoctorProvisionRequest, LeaveCreate, WorkingHourCreate
from app.services.doctor import DoctorManagementService

DEMO_DOCTORS: tuple[dict[str, object], ...] = (
    {
        "full_name": "Dr Anaya Rao Demo",
        "email": "anaya.rao@demo.careloop",
        "specialisation": "Cardiology",
        "qualifications": "MBBS, MD (General Medicine), DM (Cardiology)",
        "biography": "Fictional demo cardiologist focused on preventive heart care and clear patient education.",
        "consultation_mode": "hybrid",
        "location": "CareLoop Demo Heart Centre, Bengaluru",
        "slot_duration_minutes": 30,
    },
    {
        "full_name": "Dr Kabir Sen Demo",
        "email": "kabir.sen@demo.careloop",
        "specialisation": "Dermatology",
        "qualifications": "MBBS, MD (Dermatology)",
        "biography": "Fictional demo dermatologist interested in evidence-based skin and hair care.",
        "consultation_mode": "video",
        "location": "CareLoop Demo Virtual Clinic",
        "slot_duration_minutes": 20,
    },
    {
        "full_name": "Dr Mira Iyer Demo",
        "email": "mira.iyer@demo.careloop",
        "specialisation": "General Medicine",
        "qualifications": "MBBS, MD (General Medicine)",
        "biography": "Fictional demo physician providing adult primary care and chronic-disease support.",
        "consultation_mode": "in_person",
        "location": "CareLoop Demo Community Clinic, Bengaluru",
        "slot_duration_minutes": 30,
    },
    {
        "full_name": "Dr Tara Nair Demo",
        "email": "tara.nair@demo.careloop",
        "specialisation": "Paediatrics",
        "qualifications": "MBBS, MD (Paediatrics)",
        "biography": "Fictional demo paediatrician focused on family-centred preventive care.",
        "consultation_mode": "hybrid",
        "location": "CareLoop Demo Children’s Clinic, Bengaluru",
        "slot_duration_minutes": 20,
    },
    {
        "full_name": "Dr Dev Malhotra Demo",
        "email": "dev.malhotra@demo.careloop",
        "specialisation": "Neurology",
        "qualifications": "MBBS, MD (General Medicine), DM (Neurology)",
        "biography": "Fictional demo neurologist supporting patients with headache and movement concerns.",
        "consultation_mode": "in_person",
        "location": "CareLoop Demo Neuro Centre, Bengaluru",
        "slot_duration_minutes": 30,
    },
    {
        "full_name": "Dr Leela Kapoor Demo",
        "email": "leela.kapoor@demo.careloop",
        "specialisation": "Orthopaedics",
        "qualifications": "MBBS, MS (Orthopaedics)",
        "biography": "Fictional demo orthopaedic surgeon interested in mobility and non-operative recovery.",
        "consultation_mode": "hybrid",
        "location": "CareLoop Demo Mobility Clinic, Bengaluru",
        "slot_duration_minutes": 20,
    },
)


@dataclass(frozen=True)
class SeedResult:
    created: int
    skipped: int


def seed_demo_data(
    db: Session,
    password: str,
    *,
    today: date | None = None,
) -> SeedResult:
    created = 0
    skipped = 0
    reference_date = today or date.today()
    users = UserRepository(db)
    doctors = DoctorManagementService(db)

    for index, demo in enumerate(DEMO_DOCTORS):
        email = str(demo["email"])
        if users.get_by_email(email):
            skipped += 1
            continue

        data = DoctorProvisionRequest(
            **demo,
            initial_password=password,
            timezone="Asia/Kolkata",
            is_available_for_booking=True,
        )
        profile = doctors.provision(data)
        for day_of_week in range(6):
            doctors.add_working_hour(
                profile.id,
                WorkingHourCreate(
                    day_of_week=day_of_week,
                    start_time=time(9),
                    end_time=time(13),
                ),
            )
            doctors.add_working_hour(
                profile.id,
                WorkingHourCreate(
                    day_of_week=day_of_week,
                    start_time=time(14),
                    end_time=time(17),
                ),
            )
        doctors.add_leave(
            profile.id,
            LeaveCreate(
                leave_date=reference_date + timedelta(days=30 + index),
                reason="Fictional demo leave",
            ),
        )
        db.commit()
        created += 1

    return SeedResult(created=created, skipped=skipped)


def main() -> None:
    explicit_environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if explicit_environment == "production" or settings.environment == "production":
        raise SystemExit("Demo data seeding is disabled in production.")

    password = os.getenv("DEMO_DOCTOR_PASSWORD")
    if not password:
        raise SystemExit("Set DEMO_DOCTOR_PASSWORD before running the demo seed command.")

    with SessionLocal() as db:
        try:
            result = seed_demo_data(db, password)
        except ValidationError:
            raise SystemExit(
                "Demo seed validation failed; check DEMO_DOCTOR_PASSWORD requirements."
            ) from None
    print(f"Demo seed complete: created={result.created}, skipped={result.skipped}")


if __name__ == "__main__":
    main()
