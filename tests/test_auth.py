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
