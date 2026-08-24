"""Supervise the constrained, single-service Render assessment topology.

This is intentionally not the production topology. Production runs the API and
each durable-job worker as independent processes; this command co-locates them
only where a free hosting plan cannot create background-worker services.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass


LOGGER = logging.getLogger(__name__)
DEFAULT_PORT = "8000"
SHUTDOWN_GRACE_SECONDS = 15.0


@dataclass(frozen=True)
class ChildSpec:
    name: str
    command: list[str]


def build_child_specs(port: str | None = None) -> list[ChildSpec]:
    """Return the three continuous child commands without starting them."""
    resolved_port = port or os.environ.get("PORT") or DEFAULT_PORT
    return [
        ChildSpec("API process", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", resolved_port]),
        ChildSpec("notification worker", [sys.executable, "-m", "app.cli.run_notification_worker"]),
        ChildSpec("Calendar worker", [sys.executable, "-m", "app.cli.run_calendar_worker"]),
    ]


def run_migrations(run: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run) -> bool:
    """Run migrations once before any child begins; failures prevent startup."""
    result = run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    if result.returncode != 0:
        LOGGER.error("database migrations failed; demo service will not start")
        return False
    return True


def _shutdown(children: Mapping[str, subprocess.Popen[object]], grace_seconds: float) -> None:
    """Stop live children, escalating only processes that outlive the grace period."""
    live = {name: child for name, child in children.items() if child.poll() is None}
    for child in live.values():
        child.terminate()

    deadline = time.monotonic() + grace_seconds
    for name, child in live.items():
        remaining = max(0.0, deadline - time.monotonic())
        try:
            child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            if child.poll() is None:
                child.kill()
                child.wait()


def supervise(
    *,
    popen: Callable[..., subprocess.Popen[object]] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    grace_seconds: float = SHUTDOWN_GRACE_SECONDS,
) -> int:
    """Start all children, returning nonzero if one exits unexpectedly."""
    children: dict[str, subprocess.Popen[object]] = {}
    shutting_down = False

    def request_shutdown(_signum: int, _frame: object) -> None:
        nonlocal shutting_down
        if not shutting_down:
            shutting_down = True
            LOGGER.info("shutdown initiated")

    previous_handlers = {sig: signal.signal(sig, request_shutdown) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for spec in build_child_specs():
            children[spec.name] = popen(spec.command, env=os.environ.copy())
            LOGGER.info("%s started", spec.name)

        while not shutting_down:
            for name, child in children.items():
                exit_code = child.poll()
                if exit_code is not None:
                    LOGGER.error("%s exited unexpectedly with code %s", name, exit_code)
                    _shutdown(children, grace_seconds)
                    return 1
            sleep(0.2)

        _shutdown(children, grace_seconds)
        return 0
    except Exception:
        # Do not include command arguments or environment content in diagnostics.
        LOGGER.exception("demo service could not start")
        _shutdown(children, grace_seconds)
        return 1
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not run_migrations():
        raise SystemExit(1)
    raise SystemExit(supervise())


if __name__ == "__main__":
    main()
