from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


def _parse_dt(value):
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _schedule_timezone(schedule):
    name = schedule.get("timezone")
    if not name:
        return None
    return ZoneInfo(name)


def _align_datetime(value, target_tz):
    if target_tz is None:
        if value.tzinfo is None:
            return value
        return value.astimezone().replace(tzinfo=None)
    if value.tzinfo is None:
        return value.astimezone(target_tz)
    return value.astimezone(target_tz)


def next_run_at(job, after):
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") in ("done", "failed"):
            return None
        return _parse_dt(sched["run_at"])
    schedule_tz = _schedule_timezone(sched)
    return croniter(
        sched["cron"],
        _align_datetime(after, schedule_tz),
    ).get_next(datetime)


def is_due(job, now):
    if not job.get("enabled", True):
        return False
    if job.get("status") == "running":
        return False
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") != "pending":
            return False
        target = _parse_dt(sched["run_at"])
        return _align_datetime(now, target.tzinfo) >= target
    # recurring: rely on precomputed next_run_at; if absent, compute from cron
    nxt = job.get("next_run_at")
    schedule_tz = _schedule_timezone(sched)
    target = _parse_dt(nxt) if nxt else croniter(
        sched["cron"],
        _align_datetime(now, schedule_tz),
    ).get_prev(datetime)
    return _align_datetime(now, target.tzinfo) >= target


def validate_schedule(schedule, now=None):
    stype = schedule.get("type")
    if stype == "once":
        try:
            run_at = _parse_dt(schedule["run_at"])
        except (ValueError, KeyError, TypeError):
            return "Invalid one-time date/time."
        if now is not None and run_at <= _align_datetime(now, run_at.tzinfo):
            return "One-time date/time must be in the future."
        return None
    if stype == "recurring":
        try:
            croniter(schedule["cron"])
        except (ValueError, KeyError, TypeError):
            return "Invalid cron expression."
        try:
            _schedule_timezone(schedule)
        except (ZoneInfoNotFoundError, TypeError):
            return "Invalid schedule timezone."
        return None
    return "Unknown schedule type."
