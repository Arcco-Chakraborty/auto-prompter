# tests/test_service.py
from datetime import datetime
from auto_prompter.store import JobStore
from auto_prompter.service import create_job, tick


def _store(tmp_path):
    return JobStore(tmp_path / "jobs.json")


def test_create_job_validates_and_defaults(tmp_path):
    store = _store(tmp_path)
    data = {"prompt": "hi",
            "target": {"type": "new", "folder": "/x"},
            "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    job, err = create_job(store, data)
    assert err is None
    assert job["id"]
    assert job["enabled"] is True
    assert job["status"] == "pending"
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
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}})

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
        "schedule": {"type": "recurring", "cron": "0 9 * * *"}})

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
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}})
    fired = tick(store, tmp_path / "logs",
                 datetime(2026, 6, 25, 9, 0, 0), run_job=lambda j, d: None)
    assert fired == []
