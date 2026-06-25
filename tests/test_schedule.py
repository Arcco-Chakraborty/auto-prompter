from datetime import datetime
from auto_prompter.schedule import next_run_at, is_due, validate_schedule


def test_once_due_when_past():
    job = {"enabled": True, "status": "pending",
           "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 10, 0, 1)) is True
    assert is_due(job, datetime(2026, 6, 25, 9, 59, 0)) is False


def test_once_not_due_when_done():
    job = {"enabled": True, "status": "done",
           "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 11, 0, 0)) is False


def test_disabled_never_due():
    job = {"enabled": False, "status": "pending",
           "schedule": {"type": "once", "run_at": "2020-01-01T00:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 11, 0, 0)) is False


def test_recurring_next_run_strictly_after():
    job = {"enabled": True, "status": "pending",
           "schedule": {"type": "recurring", "cron": "0 9 * * *"}}
    nxt = next_run_at(job, datetime(2026, 6, 25, 9, 0, 0))
    assert nxt == datetime(2026, 6, 26, 9, 0, 0)


def test_recurring_due_uses_next_run_at_field():
    job = {"enabled": True, "status": "pending",
           "next_run_at": "2026-06-25T09:00:00",
           "schedule": {"type": "recurring", "cron": "0 9 * * *"}}
    assert is_due(job, datetime(2026, 6, 25, 9, 0, 1)) is True
    assert is_due(job, datetime(2026, 6, 25, 8, 59, 0)) is False


def test_validate_schedule():
    assert validate_schedule({"type": "recurring", "cron": "0 9 * * *"}) is None
    assert validate_schedule({"type": "recurring", "cron": "not a cron"}) is not None
    assert validate_schedule({"type": "once", "run_at": "2026-06-25T10:00:00"}) is None
    assert validate_schedule({"type": "once", "run_at": "nonsense"}) is not None
