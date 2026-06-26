# Server Deployment with Login — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an env-gated password login to Auto_Prompter, then deploy it to the Oracle VM behind nginx+HTTPS so scheduled Claude prompts fire overnight with the laptop off.

**Architecture:** Phase A adds a small `auth.py` (env-gated `login_required`) + login page to the Flask app, fully TDD'd, defaulting OFF so local dev and the existing 57 tests are unaffected. Phase B is an operational runbook: remove cbc-task, add swap, install+login the `claude` CLI, deploy via gunicorn/systemd (1 worker), and front it with nginx + Let's Encrypt on a duckdns subdomain.

**Tech Stack:** Flask, gunicorn, systemd, nginx, certbot, werkzeug password hashing, duckdns, Claude Code CLI.

**Spec:** `docs/superpowers/specs/2026-06-26-server-deployment-with-login-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `auto_prompter/auth.py` | NEW. `login_enabled()`, `check_password()`, `login_required` decorator. Reads env. |
| `templates/login.html` | NEW. Minimal password form. |
| `app.py` | MODIFY. Secret key + cookie flags; `/login`, `/logout` routes; decorate protected routes. |
| `wsgi.py` | NEW. gunicorn entry point that builds the app from disk paths. |
| `tests/test_auth.py` | NEW. Gate-off-by-default, redirect, correct/wrong password, api protection, logout. |
| `requirements.txt` | MODIFY. Add `gunicorn`. |
| `.gitignore` | MODIFY. Add `.env`. |
| `deploy/auto-prompter.service` | NEW. systemd unit (committed for reference). |
| `deploy/nginx-auto-prompter.conf` | NEW. nginx site (committed for reference). |

---

# Phase A — Repo code (TDD)

### Task 1: Auth module — gate disabled by default

**Files:**
- Create: `auto_prompter/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auto_prompter.auth'`

- [ ] **Step 3: Write minimal implementation**

```python
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


def login_required(view):
    """Redirect unauthenticated requests to the login page when gating is on."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if login_enabled() and not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/auth.py tests/test_auth.py
git commit -m "feat: env-gated auth module (login_required, check_password)"
```

---

### Task 2: Wire login into the Flask app

**Files:**
- Modify: `app.py`
- Create: `templates/login.html`
- Test: `tests/test_auth.py` (add route-level tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL — login route 404 / no redirect.

- [ ] **Step 3: Create the login template**

```html
<!-- templates/login.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Prompter — Login</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <h1>Auto Prompter</h1>
  <section class="card">
    <h2>Log in</h2>
    <form method="post" action="{{ url_for('login') }}">
      <label>Password
        <input type="password" name="password" autofocus required>
      </label>
      <button type="submit">Log in</button>
      {% if error %}<span class="error">{{ error }}</span>{% endif %}
    </form>
  </section>
</body>
</html>
```

- [ ] **Step 4: Modify `app.py`**

Add the import near the other `auto_prompter` imports:

```python
import os
import secrets

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from auto_prompter import auth as auth_mod
```

Inside `create_app`, right after `app = Flask(__name__)`, add session config:

```python
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AUTO_PROMPTER_HTTPS") == "1",
    )
```

Add the login/logout routes (place them before `return app`):

```python
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if auth_mod.check_password(request.form.get("password", "")):
                session["authed"] = True
                nxt = request.args.get("next") or url_for("index")
                return redirect(nxt)
            return render_template("login.html", error="Invalid password"), 401
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
```

Decorate the protected routes by adding `@auth_mod.login_required` directly under
each route decorator. The routes to protect: `index`, `api_sessions`,
`api_browse`, `api_jobs`, `api_create_job`, `api_delete_job`, `api_toggle_job`,
`api_job_log`. Example for the first two:

```python
    @app.get("/")
    @auth_mod.login_required
    def index():
        return render_template("index.html")

    @app.get("/api/sessions")
    @auth_mod.login_required
    def api_sessions():
        return jsonify(sessions_mod.discover_sessions())
```

Apply the same `@auth_mod.login_required` line (immediately under the
`@app....` decorator) to every remaining route in the list above. Do NOT
decorate `login`, `logout`, or static.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Run the full suite (nothing else broke)**

Run: `./venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 66 passed (57 existing + 9 new). The existing `test_app.py`
tests don't set `AUTO_PROMPTER_AUTH`, so the gate stays off for them.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/login.html tests/test_auth.py
git commit -m "feat: add login/logout routes and protect API behind env-gated auth"
```

---

### Task 3: gunicorn entry point + deps + gitignore

**Files:**
- Create: `wsgi.py`
- Modify: `requirements.txt`, `.gitignore`

- [ ] **Step 1: Create `wsgi.py`**

```python
# wsgi.py — gunicorn entry point.
#
# Run with ONE worker only: the app starts a background scheduler thread, and
# multiple workers would each run their own scheduler and double-fire jobs.
#   gunicorn -w 1 -b 127.0.0.1:5055 wsgi:app
from pathlib import Path

from app import create_app
from auto_prompter.service import Scheduler
from auto_prompter.store import JobStore

_base = Path(__file__).resolve().parent
_store = JobStore(_base / "jobs.json")
_logs_dir = _base / "logs"

_scheduler = Scheduler(_store, _logs_dir)
_scheduler.start()

app = create_app(_store, _logs_dir)
```

- [ ] **Step 2: Verify it imports**

Run: `./venv/Scripts/python.exe -c "import wsgi; print(type(wsgi.app))"`
Expected: `<class 'flask.app.Flask'>`

- [ ] **Step 3: Add gunicorn to requirements**

Append to `requirements.txt`:

```
gunicorn==23.0.0
```

(gunicorn is Linux-only; it is for the server. Local Windows dev keeps using
`python app.py`. Installing it locally is optional — `pip install gunicorn` may
warn on Windows; that's fine.)

- [ ] **Step 4: Add `.env` to `.gitignore`**

Add this line to `.gitignore`:

```
.env
```

- [ ] **Step 5: Commit**

```bash
git add wsgi.py requirements.txt .gitignore
git commit -m "feat: add gunicorn wsgi entry point (single scheduler) and ignore .env"
```

---

### Task 4: Commit deploy reference files

**Files:**
- Create: `deploy/auto-prompter.service`, `deploy/nginx-auto-prompter.conf`

- [ ] **Step 1: Create the systemd unit**

```ini
# deploy/auto-prompter.service -> /etc/systemd/system/auto-prompter.service
[Unit]
Description=Auto Prompter (Flask + scheduler)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/auto-prompter
EnvironmentFile=/home/ubuntu/auto-prompter/.env
ExecStart=/home/ubuntu/auto-prompter/venv/bin/gunicorn -w 1 -b 127.0.0.1:5055 --timeout 120 wsgi:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create the nginx site**

```nginx
# deploy/nginx-auto-prompter.conf -> /etc/nginx/conf.d/auto-prompter.conf
# Raw IP and bare HTTP -> redirect to the HTTPS duckdns domain.
server {
    listen 80 default_server;
    server_name _;
    return 301 https://AUTOPROMPT_DOMAIN$request_uri;
}

server {
    listen 443 ssl;
    server_name AUTOPROMPT_DOMAIN;

    # certbot fills in ssl_certificate / ssl_certificate_key on first run.

    client_max_body_size 5M;

    location / {
        proxy_pass http://127.0.0.1:5055;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Note: `AUTOPROMPT_DOMAIN` is replaced with the real duckdns hostname during
Phase B Task 9. The existing blackmoniker/arctronas `sites-enabled` server
blocks have explicit `server_name`s, so making this `listen 80 default_server`
only captures unmatched hosts (the raw IP) and does not hijack them. The old
`cbc-task.conf` (also `default_server`) is removed in Task 6, so there is no
duplicate-default conflict.

- [ ] **Step 3: Commit**

```bash
git add deploy/
git commit -m "chore: add systemd + nginx deploy reference files"
```

- [ ] **Step 4: Push Phase A**

```bash
git push origin main
```

---

# Phase B — Server deployment (operational runbook)

> These run over SSH:
> `ssh -i "D:/Projects/Server/ssh-key-2026-03-17 (1).key" ubuntu@144.24.104.158`
> Each step lists the command and what success looks like. Stop and report if a
> verification fails.

### Task 5: Pre-flight snapshot

- [ ] **Step 1: Record current state (rollback baseline)**

Run on server:
```bash
pm2 list
ls /etc/nginx/conf.d/ /etc/nginx/sites-enabled/
free -h
sudo nginx -t
```
Expected: `blackmoniker`, `cbc-task` online; `cbc-task.conf` present; nginx OK.
Save this output before changing anything.

---

### Task 6: Back up and remove cbc-task

- [ ] **Step 1: Back up**

```bash
ts=$(date +%Y%m%d-%H%M%S)
tar czf /home/ubuntu/backups/cbc-task-$ts.tar.gz -C /home/ubuntu cbc-task
ls -lh /home/ubuntu/backups/cbc-task-*.tar.gz
```
Expected: a new tarball listed.

- [ ] **Step 2: Remove PM2 process + nginx config + dir**

```bash
pm2 delete cbc-task && pm2 save
sudo rm /etc/nginx/conf.d/cbc-task.conf
sudo nginx -t && sudo systemctl reload nginx
rm -rf /home/ubuntu/cbc-task
```
Expected: `nginx -t` OK; `pm2 list` no longer shows cbc-task; blackmoniker still
online.

- [ ] **Step 3: Verify survivors**

```bash
pm2 list
curl -sI https://blackmoniker.com | head -1
curl -sI https://arctronas.duckdns.org | head -1
```
Expected: blackmoniker online; both return `HTTP/.. 200` (or expected redirect).

---

### Task 7: Add swap (claude needs headroom on 1 GB)

- [ ] **Step 1: Create a 2 GB swapfile**

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```
Expected: `free -h` shows ~2.0Gi swap total.

---

### Task 8: Install + authenticate the Claude CLI

- [ ] **Step 1: Install**

```bash
sudo npm i -g @anthropic-ai/claude-code
claude --version
```
Expected: prints a version.

- [ ] **Step 2: Subscription login (interactive, one-time)**

```bash
claude   # or: claude login
```
Follow the printed URL on your laptop, paste the code back. This uses the
existing subscription (no API key).

- [ ] **Step 3: Verify a headless prompt works**

```bash
mkdir -p /home/ubuntu/autoprompt-workspace
cd /home/ubuntu/autoprompt-workspace
claude -p "reply with the single word: ready"
```
Expected: output contains `ready`. If it errors with auth, re-run Step 2.

---

### Task 9: Deploy the app

- [ ] **Step 1: Push the working dir from the laptop (run locally, not on server)**

```bash
rsync -az --delete \
  --exclude venv --exclude .git --exclude logs --exclude jobs.json --exclude __pycache__ \
  -e 'ssh -i "D:/Projects/Server/ssh-key-2026-03-17 (1).key"' \
  D:/Projects/Auto_Prompter/ ubuntu@144.24.104.158:/home/ubuntu/auto-prompter/
```
Expected: files transfer; no errors.

- [ ] **Step 2: Create venv + install (on server)**

```bash
cd /home/ubuntu/auto-prompter
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m pytest -q
```
Expected: 66 passed.

- [ ] **Step 3: Generate password + write `.env` (on server)**

```bash
cd /home/ubuntu/auto-prompter
PW=$(venv/bin/python -c "import secrets; print(secrets.token_urlsafe(18))")
HASH=$(venv/bin/python -c "import sys; from werkzeug.security import generate_password_hash as g; print(g(sys.argv[1]))" "$PW")
SECRET=$(venv/bin/python -c "import secrets; print(secrets.token_hex(32))")
cat > .env <<EOF
SECRET_KEY=$SECRET
APP_PASSWORD_HASH=$HASH
AUTO_PROMPTER_AUTH=1
AUTO_PROMPTER_HTTPS=1
EOF
chmod 600 .env
echo "APP PASSWORD (save now, shown once): $PW"
```
Expected: prints the password once. Record it in a password manager. The
plaintext is never stored on disk — only the hash in `.env`.

- [ ] **Step 4: Install + start the systemd service**

```bash
sudo cp deploy/auto-prompter.service /etc/systemd/system/auto-prompter.service
sudo systemctl daemon-reload
sudo systemctl enable --now auto-prompter
sudo systemctl status auto-prompter --no-pager
curl -sI http://127.0.0.1:5055/ | head -1
```
Expected: service `active (running)`; curl returns `302` (redirect to /login).

---

### Task 10: DNS + TLS + nginx

> Prerequisite: a duckdns subdomain + token from the user. Let `AUTOPROMPT_DOMAIN`
> be e.g. `autoprompt.duckdns.org`.

- [ ] **Step 1: Point duckdns at the server IP**

```bash
curl "https://www.duckdns.org/update?domains=SUBDOMAIN&token=DUCKDNS_TOKEN&ip=144.24.104.158"
```
Expected: `OK`. Confirm: `dig +short AUTOPROMPT_DOMAIN` → `144.24.104.158`.

- [ ] **Step 2: Install the nginx site (with the real domain)**

```bash
cd /home/ubuntu/auto-prompter
sudo sed "s/AUTOPROMPT_DOMAIN/autoprompt.duckdns.org/g" \
  deploy/nginx-auto-prompter.conf | sudo tee /etc/nginx/conf.d/auto-prompter.conf
sudo nginx -t && sudo systemctl reload nginx
```
Expected: `nginx -t` OK. (The `listen 443 ssl` block will not fully load until
certs exist; certbot adds them next. If `nginx -t` complains about missing
cert, proceed to Step 3 which provisions it, then reload.)

- [ ] **Step 3: Get the certificate**

```bash
sudo certbot --nginx -d autoprompt.duckdns.org --non-interactive --agree-tos -m YOUR_EMAIL
sudo nginx -t && sudo systemctl reload nginx
```
Expected: certbot success; cert installed; nginx reloads clean.

---

### Task 11: End-to-end verification

- [ ] **Step 1: Routing + redirect**

```bash
curl -sI http://144.24.104.158/ | head -1          # expect 301 to https domain
curl -sI https://autoprompt.duckdns.org/ | head -1 # expect 302 to /login
curl -sI https://blackmoniker.com | head -1        # still alive
curl -sI https://arctronas.duckdns.org | head -1   # still alive
```

- [ ] **Step 2: Login in a browser**

Open `https://autoprompt.duckdns.org`, confirm the login page, wrong password
rejected, correct password reaches the dashboard.

- [ ] **Step 3: Live scheduled prompt (the real goal)**

In the UI: schedule a **one-time** prompt ~2 minutes out, target **new chat** in
`/home/ubuntu/autoprompt-workspace`, prompt e.g. `write the word hello to a file
named proof.txt`. Wait, then:
```bash
cat /home/ubuntu/auto-prompter/logs/*.log | tail -20
ls /home/ubuntu/autoprompt-workspace/
```
Expected: the job log shows the claude invocation and output; it fired **once**
(not twice — confirms single worker); `proof.txt` exists.

- [ ] **Step 4: Reboot survival (optional but recommended)**

```bash
sudo reboot
# reconnect after ~30s
systemctl is-active auto-prompter   # expect: active
pm2 list                            # blackmoniker back online
```

---

## Self-Review

**Spec coverage:**
- Remove cbc-task + back up → Task 6 ✓
- Auto_Prompter on raw-IP root → Task 4 (default_server) + Task 10 ✓
- Subscription Claude login → Task 8 ✓
- duckdns + HTTPS, raw IP redirects → Task 10 + Task 11 Step 1 ✓
- Single password, hashed in .env → Task 9 Step 3 ✓
- Login code committed, env-gated → Tasks 1–2 ✓
- Generated password shown once → Task 9 Step 3 ✓
- gunicorn systemd 1 worker (no double-fire) → Task 3 + Task 4 + Task 11 Step 3 ✓
- 2 GB swap → Task 7 ✓
- Auth-failure visible in logs → existing runner log capture + Task 11 Step 3 ✓
- Tests for auth → Tasks 1–2 ✓
- `.env` git-ignored → Task 3 ✓

**Placeholder scan:** Operational placeholders (`AUTOPROMPT_DOMAIN`, `SUBDOMAIN`,
`DUCKDNS_TOKEN`, `YOUR_EMAIL`) are intentional values supplied at deploy time,
flagged inline — not code-plan gaps. No code steps lack code.

**Type consistency:** `login_enabled()`, `check_password()`, `login_required`
names match across auth.py, app.py, and tests. Endpoint name `login` matches the
decorator's `url_for("login")`. `wsgi:app` matches the systemd `ExecStart`.
Port `5055` consistent across wsgi note, systemd unit, nginx proxy_pass, and
verification curls.
