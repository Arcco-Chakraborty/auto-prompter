# Auto_Prompter — Server Deployment with Login

**Date:** 2026-06-26
**Status:** Approved design (pending user spec review)

## Goal

Run Auto_Prompter on the user's Oracle Cloud VM so scheduled Claude prompts fire
overnight **with the laptop off**, reachable at a secure URL, gated by a login.

## Context

- **Server:** Oracle Cloud, `144.24.104.158`, Ubuntu 22.04, 2 vCPU, ~1 GB RAM,
  **no swap**. Node 20.20, Python 3.10.12, nginx, PM2, certbot already present.
- **Live apps that must keep working:** `blackmoniker` (PM2, :3200) and
  `arctronas` (systemd + gunicorn, :5000).
- **Being removed:** `cbc-task` (PM2 :8080, raw-IP root, `conf.d/cbc-task.conf`).
- **SSH:** `ssh -i "D:/Projects/Server/ssh-key-2026-03-17 (1).key" ubuntu@144.24.104.158`
- The app shells out to `claude -p "..."`; it does not read Claude's replies.

## Key decisions (from brainstorming)

| Decision | Choice |
|----------|--------|
| Claude auth on server | **Subscription login** (headless, over SSH) — uses existing plan, no per-token API billing |
| Reachability | **Remove cbc-task**, Auto_Prompter takes the raw-IP root; only blackmoniker + arctronas survive |
| Transport/TLS | **Free duckdns subdomain + Let's Encrypt HTTPS**; raw IP / port 80 → 301 redirect to the HTTPS domain |
| Login model | **Single password**, bcrypt/werkzeug **hash** in server `.env`; Flask session cookie |
| Login code location | **Committed to the repo**, gated by an env flag so local dev isn't forced to log in |
| Password provisioning | **Generated strong password**, hash stored on server, shown to user once |
| Process model | **gunicorn under systemd, 1 worker** (avoids double-firing the scheduler) |

## Architecture

```
Browser ──HTTPS──> nginx (:443, autoprompt.duckdns.org)
                     │  proxy_pass
                     ▼
              gunicorn (127.0.0.1:5055, 1 worker)
                     │
              Flask app (create_app)
                ├── @login_required on all routes except /login + static
                ├── background scheduler thread (fires due jobs)
                └── runner → subprocess: `claude -p "..."` (+ settings flags)
                                  │
                            authenticated claude CLI (subscription)

http://144.24.104.158  ──80──> nginx 301 redirect ──> https://autoprompt.duckdns.org
```

### Why 1 gunicorn worker (critical)

Auto_Prompter starts a background scheduler thread inside the process. Under
gunicorn with N workers, each worker process starts its **own** scheduler, so
every due job fires N times. Single-user traffic does not need more than one
worker, so we run exactly one. (If concurrency is ever needed, the scheduler
must be split into a separate single-instance process; out of scope now.)

## Components

### New code in the repo (committed, tested)

1. **`auto_prompter/auth.py`**
   - `login_required(view)` decorator: redirects to `/login` when no valid
     session and login is enabled.
   - `check_password(raw)` — `werkzeug.security.check_password_hash` against
     `APP_PASSWORD_HASH`.
   - `login_enabled()` — true when `AUTO_PROMPTER_AUTH=1` (or a password hash is
     configured). Off by default so local dev and the existing test suite are
     unaffected.

2. **`templates/login.html`** — minimal password form posting to `/login`.

3. **`app.py` wiring**
   - `SECRET_KEY` from env (random fallback in dev).
   - Session cookie flags: `SESSION_COOKIE_HTTPONLY=True`,
     `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE=True` when
     `AUTO_PROMPTER_HTTPS=1`.
   - Routes: `GET/POST /login`, `POST /logout`.
   - Apply `login_required` to `/`, all `/api/*` routes (including `/api/browse`
     and `/api/sessions`, which expose the server filesystem).

4. **`tests/test_auth.py`** — covers: gate off by default; gated routes 302 to
   `/login` when enabled; correct password sets session and grants access; wrong
   password rejected; `/api/*` protected; logout clears session.

### Config (server `.env`, git-ignored)

```
SECRET_KEY=<random 32+ bytes>
APP_PASSWORD_HASH=<werkzeug pbkdf2/scrypt hash>
AUTO_PROMPTER_AUTH=1
AUTO_PROMPTER_HTTPS=1
```

`.env` is loaded on the server only. `.gitignore` already covers `*.log`; add
`.env` to it.

## Deployment runbook (executed at implementation time)

1. **Back up & remove cbc-task**
   - `tar czf /home/ubuntu/backups/cbc-task-<ts>.tar.gz -C /home/ubuntu cbc-task`
   - `pm2 delete cbc-task && pm2 save`
   - `sudo rm /etc/nginx/conf.d/cbc-task.conf`; remove `/home/ubuntu/cbc-task`
2. **System prep**
   - Add **2 GB swapfile** (`/swapfile`, `swapon`, persist in `/etc/fstab`).
3. **Claude CLI**
   - `sudo npm i -g @anthropic-ai/claude-code`
   - Headless **subscription** login over SSH; verify `claude -p "say hi"` works
     in a test folder.
4. **Deploy app**
   - rsync repo → `/home/ubuntu/auto-prompter/` (over the existing SSH key).
   - `python3 -m venv venv && venv/bin/pip install -r requirements.txt`
   - add `gunicorn` to requirements.
   - Write server `.env` (generate password, store hash, show plaintext once).
5. **systemd**
   - `auto-prompter.service`: gunicorn `app:create_app()` factory style,
     `127.0.0.1:5055`, **1 worker**, `EnvironmentFile=.env`, `WantedBy=multi-user`.
   - enable + start; confirm boot-survival.
6. **DNS + TLS**
   - Point duckdns subdomain → `144.24.104.158` (needs user's duckdns
     subdomain + token).
   - `certbot --nginx -d autoprompt.duckdns.org`.
7. **nginx**
   - New site: `443` server for the domain → `proxy_pass 127.0.0.1:5055`
     (with `X-Forwarded-Proto`); make it the default and 301 the raw IP / port 80
     to the HTTPS domain.
   - `nginx -t && systemctl reload nginx`.
8. **Verify** (see below).

## Error handling

- **Claude auth expired on server:** subprocess fails; the failure (stderr) is
  already captured to the job's log file and surfaced via the **Log** button.
  Documented as the first thing to check when a night run fails.
- **OOM:** mitigated by removing cbc-task + 2 GB swap.
- **Wrong password:** generic "invalid password" (no user enumeration; it's a
  single password anyway). No lockout in v1 (single-user, HTTPS, strong
  generated password) — noted as a possible future hardening.
- **Scheduler crash:** existing loop already swallows per-tick exceptions and
  logs; systemd restarts the process if it dies.

## Testing & verification

- **Unit:** existing 57 tests stay green; new `test_auth.py` added. Auth gate
  defaults off so nothing else changes.
- **Server smoke test:**
  - `systemctl status auto-prompter` active; `curl -I http://144.24.104.158`
    → 301 to HTTPS domain.
  - `https://autoprompt.duckdns.org` → login page; wrong password rejected;
    correct password reaches the dashboard.
  - blackmoniker + arctronas still serve correctly after the nginx changes.
  - Schedule a one-time prompt ~2 min out in a server test folder; confirm it
    fires once (not twice), and the Log shows Claude output.

## Out of scope (YAGNI)

- Multi-user accounts / roles.
- Reading or acting on Claude's responses.
- Migrating laptop chat history to the server (server starts with empty history).
- Rate limiting / brute-force lockout (single password + HTTPS for v1).

## Prerequisites needed from user at deploy time

- A **duckdns subdomain + token** (free account) for DNS + TLS.
- Availability for the **one-time interactive Claude subscription login** over SSH
  (open a URL locally, paste a code back).
