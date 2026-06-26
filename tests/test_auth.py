# tests/test_auth.py
import os

from werkzeug.security import generate_password_hash

from auto_prompter import auth


def test_gate_off_by_default(monkeypatch):
    monkeypatch.delenv("AUTO_PROMPTER_AUTH", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    assert auth.login_enabled() is False


def test_gate_on_when_flag_set(monkeypatch):
    monkeypatch.setenv("AUTO_PROMPTER_AUTH", "1")
    assert auth.login_enabled() is True


def test_check_password_matches_hash(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD_HASH", generate_password_hash("s3cret"))
    assert auth.check_password("s3cret") is True
    assert auth.check_password("wrong") is False


def test_check_password_false_when_no_hash(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    assert auth.check_password("anything") is False
