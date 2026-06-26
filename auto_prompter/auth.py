# auto_prompter/auth.py
"""Optional, env-gated password login for Auto_Prompter.

Disabled by default so local development and the test suite need no login.
Enabled on the server by setting AUTO_PROMPTER_AUTH=1 and APP_PASSWORD_HASH.
"""
import os
from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash


def login_enabled():
    """True when login should be enforced (flag set, or a hash configured)."""
    if os.environ.get("AUTO_PROMPTER_AUTH") == "1":
        return True
    return bool(os.environ.get("APP_PASSWORD_HASH"))


def check_password(raw):
    """Verify ``raw`` against APP_PASSWORD_HASH. False when no hash is set."""
    hashed = os.environ.get("APP_PASSWORD_HASH", "")
    if not hashed:
        return False
    return check_password_hash(hashed, raw)


# Requires a view named "login" to be registered (see app.py).
def login_required(view):
    """Redirect unauthenticated requests to the login page when gating is on."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if login_enabled() and not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
