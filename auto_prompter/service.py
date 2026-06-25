# auto_prompter/service.py
import threading
import uuid
from datetime import datetime

from . import runner
from .schedule import is_due, next_run_at, validate_schedule


def create_job(store, data):
    schedule = data.get("schedule", {})
    err = validate_schedule(schedule)
    if err:
        return None, err
    if not data.get("prompt", "").strip():
        return None, "Prompt is required."
    target = data.get("target", {})
    if target.get("type") not in ("new", "existing"):
        return None, "Invalid target."

    job = {
        "id": uuid.uuid4().hex,
        "prompt": data["prompt"],
        "target": target,
        "schedule": schedule,
        "enabled": True,
        "status": "pending",
        "last_run_at": None,
        "last_log": None,
        "next_run_at": None,
    }
    nxt = next_run_at(job, datetime.now())
    job["next_run_at"] = nxt.isoformat(timespec="seconds") if nxt else None
    store.add(job)
    return job, None


def tick(store, logs_dir, now, run_job=runner.run_job):
    fired = []
    for job in store.list():
        if not is_due(job, now):
            continue
        result = run_job(job, logs_dir)
        fields = {
            "last_run_at": result["ran_at"],
            "last_log": result["log_path"],
        }
        if job["schedule"]["type"] == "once":
            fields["status"] = result["status"]
            fields["next_run_at"] = None
        else:
            fields["status"] = result["status"]
            nxt = next_run_at(job, now)
            fields["next_run_at"] = nxt.isoformat(timespec="seconds")
        store.update(job["id"], **fields)
        fired.append(job["id"])
    return fired


class Scheduler:
    def __init__(self, store, logs_dir, interval=15):
        self.store = store
        self.logs_dir = logs_dir
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                tick(self.store, self.logs_dir, datetime.now())
            except Exception:  # noqa: BLE001 - never let the loop die
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
