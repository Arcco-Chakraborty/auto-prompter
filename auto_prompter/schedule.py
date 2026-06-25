from datetime import datetime
from croniter import croniter


def _parse_dt(value):
    return datetime.fromisoformat(value)


def next_run_at(job, after):
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") == "done":
            return None
        return _parse_dt(sched["run_at"])
    return croniter(sched["cron"], after).get_next(datetime)


def is_due(job, now):
    if not job.get("enabled", True):
        return False
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") == "done":
            return False
        return now >= _parse_dt(sched["run_at"])
    # recurring: rely on precomputed next_run_at; if absent, compute from cron
    nxt = job.get("next_run_at")
    target = _parse_dt(nxt) if nxt else croniter(
        sched["cron"], now).get_prev(datetime)
    return now >= target


def validate_schedule(schedule):
    stype = schedule.get("type")
    if stype == "once":
        try:
            _parse_dt(schedule["run_at"])
        except (ValueError, KeyError, TypeError):
            return "Invalid one-time date/time."
        return None
    if stype == "recurring":
        try:
            croniter(schedule["cron"])
        except (ValueError, KeyError, TypeError):
            return "Invalid cron expression."
        return None
    return "Unknown schedule type."
