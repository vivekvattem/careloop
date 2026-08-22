import os
import threading
import uuid
from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import DoctorProfile, DoctorWorkingHour
from app.models.user import User, UserRole
from app.models.visit import CareDocument, CareDocumentType
from app.schemas.appointment import SymptomInput
from app.schemas.doctor import LeaveCreate
from app.services.appointment import (
    AppointmentService,
    HoldConflictError,
    InvalidSlotError,
    LeaveConflictService,
)
from app.services.visit import HistoryRetriever

pytestmark = pytest.mark.postgresql
PG_DATE = date(2099, 4, 6)
PG_ZONE = ZoneInfo("Asia/Kolkata")


def _postgres_url() -> str | None:
    configured = os.getenv("TEST_DATABASE_URL")
    if not configured:
        return None
    development_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("CARELOOP_DATABASE_URL")
    )
    if development_url and make_url(configured) == make_url(development_url):
        raise RuntimeError("TEST_DATABASE_URL must not equal the development DATABASE_URL")
    return configured


@pytest.fixture(scope="module")
def pg_sessions() -> Generator[sessionmaker[Session], None, None]:
    database_url = _postgres_url()
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL concurrency tests")

    schema = f"careloop_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))

    scoped_url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema},public"}
    )
    engine = create_engine(scoped_url)
    Base.metadata.create_all(engine, checkfirst=False)
    with engine.connect() as connection:
        assert inspect(connection).has_table("users", schema=schema)
        assert inspect(connection).has_table("appointments", schema=schema)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin_engine.dispose()


@pytest.fixture
def pg_case(pg_sessions: sessionmaker[Session]) -> dict[str, object]:
    unique = uuid.uuid4().hex
    with pg_sessions() as db:
        patient_one = User(
            full_name="Concurrency Patient One",
            email=f"p1-{unique}@example.com",
            password_hash="not-used",
            role=UserRole.PATIENT,
        )
        patient_two = User(
            full_name="Concurrency Patient Two",
            email=f"p2-{unique}@example.com",
            password_hash="not-used",
            role=UserRole.PATIENT,
        )
        doctor_user = User(
            full_name="Concurrency Doctor",
            email=f"doctor-{unique}@example.com",
            password_hash="not-used",
            role=UserRole.DOCTOR,
        )
        profile = DoctorProfile(
            user=doctor_user,
            specialisation="Concurrency Medicine",
            slot_duration_minutes=30,
            timezone="Asia/Kolkata",
            is_available_for_booking=True,
        )
        db.add_all([patient_one, patient_two, profile])
        db.flush()
        db.add(
            DoctorWorkingHour(
                doctor_profile_id=profile.id,
                day_of_week=PG_DATE.weekday(),
                start_time=time(9),
                end_time=time(11),
            )
        )
        db.commit()
        return {
            "patient_one": patient_one.id,
            "patient_two": patient_two.id,
            "doctor": profile.id,
            "start": datetime.combine(PG_DATE, time(9), PG_ZONE),
        }


def _symptoms() -> SymptomInput:
    return SymptomInput(
        chief_complaint="Concurrency test",
        symptom_description="Fictional symptoms for a concurrency test.",
        duration="One day",
        severity=3,
    )


def test_two_patients_racing_for_same_hold_get_one_success(
    pg_sessions: sessionmaker[Session], pg_case: dict[str, object]
) -> None:
    barrier = threading.Barrier(2)
    results: list[int] = []
    lock = threading.Lock()

    def worker(patient_id) -> None:
        with pg_sessions() as db:
            patient = db.get(User, patient_id)
            barrier.wait()
            try:
                AppointmentService(db).create_hold(
                    patient, pg_case["doctor"], pg_case["start"]
                )
                result = 201
            except HoldConflictError:
                result = 409
            with lock:
                results.append(result)

    threads = [
        threading.Thread(target=worker, args=(pg_case["patient_one"],)),
        threading.Thread(target=worker, args=(pg_case["patient_two"],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == [201, 409]


def test_two_confirmations_racing_consume_one_hold_and_create_one_appointment(
    pg_sessions: sessionmaker[Session], pg_case: dict[str, object]
) -> None:
    with pg_sessions() as db:
        patient = db.get(User, pg_case["patient_one"])
        hold = AppointmentService(db).create_hold(
            patient,
            pg_case["doctor"],
            pg_case["start"] + timedelta(minutes=30),
        )

    barrier = threading.Barrier(2)
    results: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        with pg_sessions() as db:
            patient = db.get(User, pg_case["patient_one"])
            barrier.wait()
            try:
                AppointmentService(db).confirm(patient, hold.hold_token, _symptoms())
                result = 201
            except HoldConflictError:
                result = 409
            with lock:
                results.append(result)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results) == [201, 409]
    with pg_sessions() as db:
        count = db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.doctor_profile_id == pg_case["doctor"],
                Appointment.status == AppointmentStatus.CONFIRMED,
            )
        )
    assert count == 1


def test_postgresql_exclusion_constraint_rejects_concurrent_active_appointments(
    pg_sessions: sessionmaker[Session], pg_case: dict[str, object]
) -> None:
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()
    start = pg_case["start"] + timedelta(minutes=60)
    end = start + timedelta(minutes=30)

    def worker(patient_id) -> None:
        with pg_sessions() as db:
            db.add(
                Appointment(
                    patient_user_id=patient_id,
                    doctor_profile_id=pg_case["doctor"],
                    slot_start=start.astimezone(timezone.utc),
                    slot_end=end.astimezone(timezone.utc),
                    status=AppointmentStatus.CONFIRMED,
                )
            )
            barrier.wait()
            try:
                db.commit()
                result = "created"
            except IntegrityError:
                db.rollback()
                result = "conflict"
            with lock:
                results.append(result)

    threads = [
        threading.Thread(target=worker, args=(pg_case["patient_one"],)),
        threading.Thread(target=worker, args=(pg_case["patient_two"],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == ["conflict", "created"]


def test_booking_and_leave_race_never_leaves_confirmed_appointment_on_leave(
    pg_sessions: sessionmaker[Session], pg_case: dict[str, object]
) -> None:
    start = pg_case["start"] + timedelta(minutes=90)
    with pg_sessions() as db:
        patient = db.get(User, pg_case["patient_one"])
        hold = AppointmentService(db).create_hold(patient, pg_case["doctor"], start)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def book() -> None:
        with pg_sessions() as db:
            patient = db.get(User, pg_case["patient_one"])
            barrier.wait()
            try:
                AppointmentService(db).confirm(patient, hold.hold_token, _symptoms())
                result = "booked"
            except (HoldConflictError, InvalidSlotError):
                result = "blocked"
            with lock:
                outcomes.append(result)

    def leave() -> None:
        with pg_sessions() as db:
            doctor_user_id = db.scalar(
                select(DoctorProfile.user_id).where(
                    DoctorProfile.id == pg_case["doctor"]
                )
            )
            barrier.wait()
            LeaveConflictService(db).apply(
                pg_case["doctor"],
                LeaveCreate(leave_date=PG_DATE, reason="Concurrency test leave"),
                confirmed=True,
                actor_user_id=doctor_user_id,
            )
            with lock:
                outcomes.append("leave")

    threads = [threading.Thread(target=book), threading.Thread(target=leave)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert "leave" in outcomes
    with pg_sessions() as db:
        confirmed = db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.doctor_profile_id == pg_case["doctor"],
                Appointment.slot_start == start.astimezone(timezone.utc),
                Appointment.status == AppointmentStatus.CONFIRMED,
            )
        )
    assert confirmed == 0


def test_postgresql_history_retrieval_is_patient_scoped_and_ranked(
    pg_sessions: sessionmaker[Session], pg_case: dict[str, object]
) -> None:
    with pg_sessions() as db:
        prior = Appointment(
            patient_user_id=pg_case["patient_one"],
            doctor_profile_id=pg_case["doctor"],
            slot_start=(pg_case["start"] - timedelta(days=30)).astimezone(timezone.utc),
            slot_end=(pg_case["start"] - timedelta(days=30) + timedelta(minutes=30)).astimezone(timezone.utc),
            status=AppointmentStatus.COMPLETED,
        )
        current = Appointment(
            patient_user_id=pg_case["patient_one"],
            doctor_profile_id=pg_case["doctor"],
            slot_start=(pg_case["start"] + timedelta(days=30)).astimezone(timezone.utc),
            slot_end=(pg_case["start"] + timedelta(days=30, minutes=30)).astimezone(timezone.utc),
            status=AppointmentStatus.COMPLETED,
        )
        other = Appointment(
            patient_user_id=pg_case["patient_two"],
            doctor_profile_id=pg_case["doctor"],
            slot_start=(pg_case["start"] - timedelta(days=60)).astimezone(timezone.utc),
            slot_end=(pg_case["start"] - timedelta(days=60) + timedelta(minutes=30)).astimezone(timezone.utc),
            status=AppointmentStatus.COMPLETED,
        )
        db.add_all([prior, current, other])
        db.flush()
        db.add_all([
            CareDocument(
                patient_user_id=pg_case["patient_one"], appointment_id=prior.id,
                document_type=CareDocumentType.CLINICAL_NOTE,
                content="Recurring fictional headache history", event_date=prior.slot_start,
                doctor_verified=True,
            ),
            CareDocument(
                patient_user_id=pg_case["patient_two"], appointment_id=other.id,
                document_type=CareDocumentType.CLINICAL_NOTE,
                content="Other patient headache history", event_date=other.slot_start,
                doctor_verified=True,
            ),
        ])
        db.commit()
        results = HistoryRetriever().retrieve(
            db,
            patient_id=pg_case["patient_one"],
            appointment_id=current.id,
            query_text="fictional headache",
        )
    assert len(results) == 1
    assert results[0][0].patient_user_id == pg_case["patient_one"]
    assert results[0][1] > 0
