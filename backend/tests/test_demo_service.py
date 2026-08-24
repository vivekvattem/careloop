from __future__ import annotations

import subprocess
import sys

from app.cli import run_demo_service


class FakeProcess:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.terminated = 0
        self.killed = 0
        self.wait_timeouts: list[float | None] = []
        self.timeout_on_wait = False
        self.exit_on_terminate = True

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated += 1
        if self.exit_on_terminate:
            self.returncode = 0

    def kill(self) -> None:
        self.killed += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.timeout_on_wait:
            self.timeout_on_wait = False
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode or 0


def test_expected_continuous_commands_use_interpreter_and_port(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "12345")
    specs = run_demo_service.build_child_specs()
    assert [spec.name for spec in specs] == ["API process", "notification worker", "Calendar worker"]
    assert all(spec.command[0] == sys.executable for spec in specs)
    assert specs[0].command[-1] == "12345"
    assert "--once" not in specs[1].command
    assert "--once" not in specs[2].command


def test_unexpected_child_exit_stops_siblings_without_logging_environment(caplog) -> None:
    created = [FakeProcess(), FakeProcess(returncode=7), FakeProcess()]
    calls: list[tuple[object, dict[str, object]]] = []

    def popen(*args, **kwargs):
        calls.append((args, kwargs))
        return created[len(calls) - 1]

    assert run_demo_service.supervise(popen=popen, sleep=lambda _: None) == 1
    assert len(calls) == 3
    assert all("shell" not in kwargs for _, kwargs in calls)
    assert created[0].terminated == 1
    assert created[2].terminated == 1
    assert "PATH=" not in caplog.text


def test_sigterm_requests_graceful_shutdown(monkeypatch) -> None:
    processes = [FakeProcess(), FakeProcess(), FakeProcess()]
    handlers: dict[object, object] = {}

    def signal_stub(sig, handler):
        handlers[sig] = handler
        return None

    monkeypatch.setattr(run_demo_service.signal, "signal", signal_stub)
    calls = 0

    def sleep(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            handlers[run_demo_service.signal.SIGTERM](15, None)

    next_process = iter(processes)
    assert run_demo_service.supervise(popen=lambda *_, **__: next(next_process), sleep=sleep) == 0
    assert all(process.terminated == 1 for process in processes) is True


def test_grace_expiry_kills_only_child_that_does_not_exit() -> None:
    exits = FakeProcess()
    stuck = FakeProcess()
    stuck.exit_on_terminate = False
    stuck.timeout_on_wait = True
    run_demo_service._shutdown({"exits": exits, "stuck": stuck}, grace_seconds=0)
    assert exits.killed == 0
    assert stuck.killed == 1


def test_migration_failure_prevents_startup(caplog) -> None:
    result = subprocess.CompletedProcess(args=[], returncode=2)
    assert run_demo_service.run_migrations(lambda *_args, **_kwargs: result) is False
    assert "database migrations failed" in caplog.text
