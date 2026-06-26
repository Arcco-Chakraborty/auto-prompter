# tests/test_auth.py
import os

from flask import Flask
from werkzeug.security import generate_password_hash

from auto_prompter import auth


def test_gate_off_by_default(monkeypatch):
    monkeypatch.delenv("AUTO_PROMPTER_AUTH", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    assert auth.login_enabled() is False


def test_gate_on_when_flag_set(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("AUTO_PROMPTER_AUTH", "1")
    assert auth.login_enabled() is True


def test_gate_on_when_hash_set_without_flag(monkeypatch):
    monkeypatch.delenv("AUTO_PROMPTER_AUTH", raising=False)
    monkeypatch.setenv("APP_PASSWORD_HASH", generate_password_hash("x"))
    assert auth.login_enabled() is True


def test_check_password_matches_hash(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD_HASH", generate_password_hash("s3cret"))
    assert auth.check_password("s3cret") is True
    assert auth.check_password("wrong") is False


def test_check_password_false_when_no_hash(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    assert auth.check_password("anything") is False


def _decorated_app():
    app = Flask(__name__)
    app.secret_key = "test"

    @app.get("/login")
    def login():
        return "login page"

    @app.get("/protected")
    @auth.login_required
    def protected():
        return "secret"

    return app


def test_login_required_allows_when_gate_off(monkeypatch):
    monkeypatch.delenv("AUTO_PROMPTER_AUTH", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    client = _decorated_app().test_client()
    resp = client.get("/protected")
    assert resp.status_code == 200
    assert resp.data == b"secret"


def test_login_required_redirects_when_gated_and_unauthed(monkeypatch):
    monkeypatch.setenv("AUTO_PROMPTER_AUTH", "1")
    client = _decorated_app().test_client()
    resp = client.get("/protected")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_required_allows_when_gated_and_authed(monkeypatch):
    monkeypatch.setenv("AUTO_PROMPTER_AUTH", "1")
    client = _decorated_app().test_client()
    with client.session_transaction() as sess:
        sess["authed"] = True
    resp = client.get("/protected")
    assert resp.status_code == 200
    assert resp.data == b"secret"


from auto_prompter.store import JobStore
from app import create_app


def _client(tmp_path, monkeypatch, password="s3cret"):
    monkeypatch.setenv("AUTO_PROMPTER_AUTH", "1")
    monkeypatch.setenv("APP_PASSWORD_HASH", generate_password_hash(password))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    store = JobStore(tmp_path / "jobs.json")
    app = create_app(store, tmp_path / "logs")
    app.config["TESTING"] = True
    return app.test_client()


def test_protected_route_redirects_to_login(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_api_route_protected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/jobs").status_code == 302


def test_login_then_access(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/login", data={"password": "s3cret"})
    assert resp.status_code == 302
    assert client.get("/").status_code == 200


def test_wrong_password_rejected(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/login", data={"password": "nope"}, follow_redirects=True)
    assert b"Invalid password" in resp.data
    assert client.get("/").status_code == 302


def test_logout_clears_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/login", data={"password": "s3cret"})
    client.post("/logout")
    assert client.get("/").status_code == 302
