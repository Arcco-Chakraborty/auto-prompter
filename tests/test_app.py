# tests/test_app.py
import json
from auto_prompter.store import JobStore
from app import create_app


def _client(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    app = create_app(store, tmp_path / "logs")
    app.config["TESTING"] = True
    return app.test_client(), store


def test_create_and_list_job(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/jobs", json={
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}})
    assert resp.status_code == 201
    job_id = resp.get_json()["id"]
    listing = client.get("/api/jobs").get_json()
    assert any(j["id"] == job_id for j in listing)


def test_create_job_validation_error(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.post("/api/jobs", json={
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "recurring", "cron": "bad"}})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_delete_job(tmp_path):
    client, _ = _client(tmp_path)
    job_id = client.post("/api/jobs", json={
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}).get_json()["id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.delete(f"/api/jobs/{job_id}").status_code == 404


def test_toggle_job(tmp_path):
    client, store = _client(tmp_path)
    job_id = client.post("/api/jobs", json={
        "prompt": "hi", "target": {"type": "new", "folder": "/x"},
        "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}).get_json()["id"]
    client.post(f"/api/jobs/{job_id}/toggle")
    assert store.get(job_id)["enabled"] is False


def test_sessions_endpoint(tmp_path, monkeypatch):
    import auto_prompter.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "discover_sessions",
                        lambda *a, **k: [{"session_id": "s", "cwd": "/c",
                                          "label": "hi", "last_used": 1.0}])
    client, _ = _client(tmp_path)
    data = client.get("/api/sessions").get_json()
    assert data[0]["session_id"] == "s"


def test_index_serves_html(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Auto Prompter" in resp.data
