import argparse
import logging
import socket
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.notifications import claim_due, deliver_job, enqueue_due_reminders

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def run_once(worker_id: str) -> int:
    with SessionLocal() as db:
        enqueue_due_reminders(db)
        jobs = claim_due(db, worker_id)
    for job in jobs:
        with SessionLocal() as db:
            deliver_job(db, job.id)
        logging.info("notification job=%s processed", job.id)
    return len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=settings.notification_poll_seconds)
    args = parser.parse_args(); worker_id = f"{socket.gethostname()}-{id(args)}"
    try:
        while True:
            run_once(worker_id)
            if args.once: return
            time.sleep(max(1, args.poll_seconds))
    except KeyboardInterrupt:
        logging.info("notification worker stopped")


if __name__ == "__main__": main()
