# auto_prompter/service.py
import logging
import shlex
import threading
import uuid
from datetime import datetime

from . import runner
from .schedule import is_due, next_run_at, validate_schedule

LOGGER = logging.getLogger(__name__)
PERMISSION_MODES = {
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
}
MAX_TIMEOUT_SECONDS = 24 * 60 * 60


def _normalize_target(target):
    if not isinstance(target, dict):
        return None, "Invalid target."
    target_type = target.get("type")
    if target_type == "new":
        folder = target.get("folder")
        if not isinstance(folder, str) or not folder.strip():
            return None, "A folder is required for a new chat."
        return {"type": "new", "folder": folder.strip()}, None
    if target_type == "existing":
        session_id = target.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return None, "An existing chat is required."
        session_folder = target.get("session_folder")
        if session_folder is not None and not isinstance(session_folder, str):
            return None, "Invalid existing-chat folder."
        return {
            "type": "existing",
            "session_id": session_id.strip(),
            "session_folder": (session_folder or "").strip(),
        }, None
    return None, "Invalid target."


def _normalize_settings(settings):
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        return None, "Invalid Claude CLI settings."

    normalized = {}
    permission_mode = settings.get("permission_mode", "")
    if not permission_mode and settings.get("dangerously_skip_permissions") is True:
        permission_mode = "bypassPermissions"
    if permission_mode:
        if permission_mode not in PERMISSION_MODES:
            return None, "Invalid permission mode."
        normalized["permission_mode"] = permission_mode

    verbose = settings.get("verbose", False)
    if not isinstance(verbose, bool):
        return None, "Verbose must be true or false."
    if verbose:
        normalized["verbose"] = True

    for field, label, limit in (
        ("model", "Model", 200),
        ("extra_flags", "Extra CLI flags", 2000),
    ):
        value = settings.get(field, "")
        if not isinstance(value, str):
            return None, f"{label} must be text."
        value = value.strip()
        if len(value) > limit:
            return None, f"{label} is too long."
        if value:
            normalized[field] = value

    if normalized.get("extra_flags"):
        try:
            shlex.split(normalized["extra_flags"])
        except ValueError:
            return None, "Extra CLI flags contain invalid quoting."

    timeout = settings.get("timeout_seconds", runner.DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool):
        return None, "Timeout must be a number of seconds."
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        return None, "Timeout must be a number of seconds."
    if not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        return None, "Timeout must be between 1 and 86400 seconds."
    normalized["timeout_seconds"] = timeout
    return normalized, None


def create_job(store, data, now=None):
    if not isinstance(data, dict):
        return None, "Invalid request."
    now = now or datetime.now().astimezone()
    schedule = data.get("schedule", {})
    if not isinstance(schedule, dict):
        return None, "Invalid schedule."
    err = validate_schedule(schedule, now=now)
    if err:
        return None, err
    prompt = data.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        return None, "Prompt is required."
    target, err = _normalize_target(data.get("target"))
    if err:
        return None, err
    settings, err = _normalize_settings(data.get("settings"))
    if err:
        return None, err

    job = {
        "id": uuid.uuid4().hex,
        "prompt": prompt,
        "target": target,
        "schedule": schedule,
        "settings": settings,
        "enabled": True,
        "status": "pending",
        "last_run_at": None,
        "last_log": None,
        "next_run_at": None,
    }
    nxt = next_run_at(job, now)
    job["next_run_at"] = nxt.isoformat(timespec="seconds") if nxt else None
    store.add(job)
    return job, None


def _record_result(store, job, result, after):
    fields = {
        "last_run_at": result["ran_at"],
        "last_log": result["log_path"],
        "status": result["status"],
    }
    if job["schedule"]["type"] == "once":
        fields["next_run_at"] = None
    else:
        nxt = next_run_at(job, after)
        fields["next_run_at"] = nxt.isoformat(timespec="seconds")
    store.update(job["id"], **fields)


def tick(store, logs_dir, now, run_job=runner.run_job):
    fired = []
    for job in store.list():
        if not is_due(job, now):
            continue
        store.update(job["id"], status="running")
        result = run_job(job, logs_dir)
        _record_result(store, job, result, now)
        fired.append(job["id"])
    return fired


class Scheduler:
    def __init__(self, store, logs_dir, interval=15):
        self.store = store
        self.logs_dir = logs_dir
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._inflight = set()
        self._inflight_lock = threading.Lock()

    def _run_claimed(self, job):
        try:
            result = runner.run_job(job, self.logs_dir)
            _record_result(self.store, job, result, datetime.now().astimezone())
        except Exception:  # noqa: BLE001 - keep scheduler alive and observable
            LOGGER.exception("Unexpected error while running job %s", job["id"])
            fallback = {
                "status": "failed",
                "log_path": None,
                "ran_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            _record_result(
                self.store, job, fallback, datetime.now().astimezone())
        finally:
            with self._inflight_lock:
                self._inflight.discard(job["id"])

    def _dispatch_due_jobs(self, now):
        for job in self.store.list():
            if not is_due(job, now):
                continue
            with self._inflight_lock:
                if job["id"] in self._inflight:
                    continue
                self._inflight.add(job["id"])
            self.store.update(job["id"], status="running")
            worker = threading.Thread(
                target=self._run_claimed,
                args=(job,),
                daemon=True,
                name=f"auto-prompter-job-{job['id'][:8]}",
            )
            worker.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._dispatch_due_jobs(datetime.now().astimezone())
            except Exception:  # noqa: BLE001 - never let the loop die
                LOGGER.exception("Unexpected error in scheduler loop")
            self._stop.wait(self.interval)

    def start(self):
        for job in self.store.list():
            if job.get("status") == "running":
                self.store.update(job["id"], status="pending")
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="auto-prompter-scheduler",
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
