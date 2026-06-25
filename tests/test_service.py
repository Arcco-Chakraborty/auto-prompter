# tests/test_service.py
from datetime import datetime
from auto_prompter.store import JobStore
import threading
import time

from auto_prompter.service import Scheduler, create_job, tick


def _store(tmp_path):
    return JobStore(tmp_path / "jobs.json")


def test_create_job_validates_and_defaults(tmp_path):
    store = _store(tmp_path)
    data = {"prompt": "hi",
            "target": {"type": "new", "folder": "/x"},
            "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    job, err = create_job(store, data, now=datetime(2026, 6, 25, 9, 0, 0))
    assert err is None
    assert job["id"]
    assert job["enabled"] is True
    assert job["status"] == "pending"
    assert job["settings"]["timeout_seconds"] == 3600
    assert store.get(job["id"]) is not None


def test_create_job_rejects_bad_cron(tmp_path):
    store = _store(tmp_path)
    data = {"prompt": "hi", "target": {"type": "new", "folder": "/x"},
            "schedule": {"type": "recurring", "cron": "bad"}}
    job, err = create_job(store, data)
    assert job is None
    assert err is not None


def test_tick_fires_due_once_job_and_marks_done(tmp_path):
    store = _store(tmp_path)
    job, _ = create_job(store, {
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}},
        now=datetime(2026, 6, 25, 9, 0, 0))

    def fake_run(j, logs_dir):
        return {"status": "done", "log_path": "logs/x.log",
                "ran_at": "2026-06-25T10:00:01"}

    fired = tick(store, tmp_path / "logs",
                 datetime(2026, 6, 25, 10, 0, 1), run_job=fake_run)
    assert fired == [job["id"]]
    stored = store.get(job["id"])
    assert stored["status"] == "done"
    assert stored["last_log"] == "logs/x.log"


def test_tick_recurring_reschedules_and_stays_enabled(tmp_path):
    store = _store(tmp_path)
    job, _ = create_job(store, {
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "recurring", "cron": "0 9 * * *"}},
        now=datetime(2026, 6, 25, 8, 0, 0))

    def fake_run(j, logs_dir):
        return {"status": "failed", "log_path": "logs/x.log",
                "ran_at": "2026-06-25T09:00:01"}

    tick(store, tmp_path / "logs",
         datetime(2026, 6, 25, 9, 0, 1), run_job=fake_run)
    stored = store.get(job["id"])
    assert stored["enabled"] is True
    assert stored["next_run_at"] == "2026-06-26T09:00:00"


def test_tick_not_due_does_nothing(tmp_path):
    store = _store(tmp_path)
    create_job(store, {
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}},
        now=datetime(2026, 6, 25, 8, 0, 0))
    fired = tick(store, tmp_path / "logs",
                 datetime(2026, 6, 25, 9, 0, 0), run_job=lambda j, d: None)
    assert fired == []


def test_failed_once_job_does_not_fire_again(tmp_path):
    store = _store(tmp_path)
    job, _ = create_job(store, {
        "prompt": "hi",
        "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"},
    }, now=datetime(2026, 6, 25, 9, 0, 0))

    calls = []

    def fake_run(j, logs_dir):
        calls.append(j["id"])
        return {
            "status": "failed",
            "log_path": "logs/x.log",
            "ran_at": "2026-06-25T10:00:01",
        }

    tick(store, tmp_path / "logs",
         datetime(2026, 6, 25, 10, 0, 1), run_job=fake_run)
    tick(store, tmp_path / "logs",
         datetime(2026, 6, 25, 10, 1, 0), run_job=fake_run)
    assert calls == [job["id"]]


def test_create_job_normalizes_inherited_settings(tmp_path):
    store = _store(tmp_path)
    job, err = create_job(store, {
        "prompt": "hi",
        "target": {
            "type": "existing",
            "session_id": "session-1",
            "session_folder": "/x",
        },
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"},
        "settings": {
            "permission_mode": "bypassPermissions",
            "model": "claude-opus-4-8",
            "timeout_seconds": "30",
        },
    }, now=datetime(2026, 6, 25, 9, 0, 0))
    assert err is None
    assert job["settings"] == {
        "permission_mode": "bypassPermissions",
        "model": "claude-opus-4-8",
        "timeout_seconds": 30,
    }


def test_scheduler_dispatches_due_jobs_without_waiting_for_each_other(
        tmp_path, monkeypatch):
    store = _store(tmp_path)
    now = datetime(2026, 6, 25, 9, 0, 0)
    for prompt in ("one", "two"):
        create_job(store, {
            "prompt": prompt,
            "target": {"type": "new", "folder": "/x"},
            "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"},
        }, now=now)

    started = []
    both_started = threading.Event()
    release = threading.Event()

    def fake_run(job, logs_dir):
        started.append(job["id"])
        if len(started) == 2:
            both_started.set()
        release.wait(2)
        return {
            "status": "done",
            "log_path": "logs/x.log",
            "ran_at": "2026-06-25T10:00:01",
        }

    monkeypatch.setattr("auto_prompter.service.runner.run_job", fake_run)
    scheduler = Scheduler(store, tmp_path / "logs")
    scheduler._dispatch_due_jobs(datetime(2026, 6, 25, 10, 0, 1))
    assert both_started.wait(1)
    release.set()
    deadline = time.time() + 2
    while time.time() < deadline:
        if all(j["status"] == "done" for j in store.list()):
            break
        time.sleep(0.01)
    assert all(j["status"] == "done" for j in store.list())
