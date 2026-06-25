# Auto Prompter — Design

**Date:** 2026-06-25
**Status:** Approved

## Summary

A local web app that sends user-specified prompts to Claude Code (the `claude`
CLI) at scheduled times. It does **not** read or react to Claude's answers — it
only delivers prompts. Each scheduled prompt either starts a **new** Claude
session in a chosen folder or **resumes an existing** session selected from a
list of discovered chats. Runs cross-platform (Linux, macOS, Windows).

## Goals

- Schedule prompts to fire **one-time** (at a datetime) or **recurring**
  (cron-style).
- Deliver each prompt **headlessly** via `claude -p "<prompt>"`.
- Target either a **new chat** (pick a working directory) or an **existing
  chat** (selected from auto-discovered sessions).
- Manage everything through a **small local web UI**.
- Work on **Windows** as well as Linux/macOS.
- Be **quick** to set up: `python app.py`.

## Non-Goals (YAGNI)

- Detecting, parsing, or reacting to Claude's responses.
- Authentication, multi-user, remote access.
- Running as a system service / OS autostart (v1 runs only while `app.py` runs).
- OS-level cron or Windows Task Scheduler integration.

## Architecture

Single Python process started with `python app.py`. It runs:

1. A **Flask web server** serving the UI and a small JSON API.
2. A **background scheduler thread** that wakes every ~15s, fires due jobs, and
   reschedules recurring ones.

State persists to a `jobs.json` file. Run output persists to per-run log files
under `logs/`.

### Modules

| Module | Responsibility | Depends on |
|--------|----------------|------------|
| `app.py` | Flask routes + API; starts scheduler thread on launch. | flask, store, sessions, scheduler |
| `scheduler.py` | Background loop; computes due jobs; one-time → fire once → `done`; recurring → fire → compute next run. | store, runner, croniter |
| `runner.py` | Builds and runs the `claude` subprocess; captures stdout/stderr to a log file; returns status. | stdlib (subprocess, shutil) |
| `sessions.py` | Scans `~/.claude/projects/*/*.jsonl`; extracts cwd, first real user message (label), last-modified time. | stdlib (pathlib, json) |
| `store.py` | CRUD for jobs persisted to `jobs.json` (atomic write). | stdlib (json, pathlib) |
| `templates/index.html`, `static/` | The web UI (form + jobs list + chats list). | — |

Each module has one clear purpose and is independently testable.

## Data Model

A **job** (stored in `jobs.json`):

```json
{
  "id": "uuid4",
  "prompt": "string",
  "target": {
    "type": "new" | "existing",
    "folder": "/abs/path",          // when type=new
    "session_id": "uuid",            // when type=existing
    "session_folder": "/abs/path"    // when type=existing (cwd to run resume in)
  },
  "schedule": {
    "type": "once" | "recurring",
    "run_at": "2026-06-26T14:30:00", // when type=once (local ISO)
    "cron": "30 9 * * *"             // when type=recurring
  },
  "enabled": true,
  "status": "pending" | "done" | "failed",
  "last_run_at": "ISO or null",
  "last_log": "logs/<id>-<ts>.log or null",
  "next_run_at": "ISO or null"       // computed for recurring/once display
}
```

## Behavior

### Session discovery (`sessions.py`)

- Path: `Path.home() / ".claude" / "projects"`.
- For each `*.jsonl`, read lines; extract `cwd` from the first line that has it;
  extract the first `type":"user"` message whose content is a plain string and
  which is **not** `isMeta` and not a `<local-command-caveat>`/tool-result line,
  truncated to ~80 chars as the label.
- Session id = filename stem. Last-used = file mtime.
- Skip non-session files (e.g. the `memory/` dir).
- Return list sorted by last-used desc.

### Scheduler (`scheduler.py`)

- Loop every ~15s.
- A job is **due** when `enabled` and:
  - once: `status == pending` and `now >= run_at`.
  - recurring: `now >= next_run_at` (computed via `croniter`).
- On fire: call `runner.run(job)`.
  - once → set `status` to `done`/`failed`, record `last_run_at`/`last_log`.
  - recurring → record `last_run_at`/`last_log`; compute next `next_run_at`;
    status stays usable (a failed run does **not** disable a recurring job).

### Runner (`runner.py`)

- Resolve binary with `shutil.which("claude")`; on Windows this finds
  `claude.cmd`. If not found → status `failed`, log the error.
- New chat: `claude -p "<prompt>"`, `cwd = target.folder`.
- Existing chat: `claude --resume <session_id> -p "<prompt>"`,
  `cwd = target.session_folder`.
- Capture stdout+stderr to `logs/<id>-<timestamp>.log`.
- Non-zero exit → `failed`.

### Web UI

- **Add-prompt form:** prompt textarea; target radio (New → folder text input |
  Existing → searchable dropdown from `/api/sessions`); schedule radio
  (One-time → datetime-local input | Recurring → preset dropdown that fills a
  raw cron field, which stays editable); Save → `POST /api/jobs`.
- **Jobs list:** each job shows prompt snippet, target, next-run, status,
  last-run, link to log; Delete + Enable/Disable. From `GET /api/jobs`.
- **Existing chats list:** refreshable; folder + label + last-used. From
  `GET /api/sessions`.

### API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | UI page |
| GET | `/api/sessions` | discovered chats |
| GET | `/api/jobs` | list jobs |
| POST | `/api/jobs` | create job |
| DELETE | `/api/jobs/<id>` | remove job |
| POST | `/api/jobs/<id>/toggle` | enable/disable |
| GET | `/api/jobs/<id>/log` | last run log text |

## Error Handling

- `claude` not found or non-zero exit → job `failed`, error written to its log,
  surfaced in the UI. Recurring jobs keep their schedule.
- Corrupt/partial `jsonl` lines are skipped during discovery (best-effort).
- `jobs.json` written atomically (temp file + replace) to avoid corruption.
- Invalid cron / past datetime → rejected at `POST /api/jobs` with a message.

## Cross-Platform Notes

- Pure Python + Flask; no tmux, no shell-isms.
- `pathlib` / `Path.home()` for the `~/.claude/projects` path.
- `shutil.which("claude")` resolves `claude.cmd` on Windows.
- In-process scheduler → identical behavior on all OSes.
- **Caveat:** prompts fire only while `python app.py` is running.

## Testing

Pytest with temp dirs and a mocked runner (no real `claude` calls):

- `sessions.py`: parse a fixture `jsonl` → correct cwd, label, sorting; skips
  meta lines and non-session files.
- `store.py`: create/read/update/delete round-trips; atomic write.
- `scheduler.py`: due-time logic for once (fires once, then done) and recurring
  (cron next-run computed; failure doesn't disable).
- `runner.py`: command construction for new vs existing; missing-binary path
  (mock `shutil.which`).

## Delivery

- `git init`, `.gitignore` (`jobs.json`, `logs/`, `venv/`, `__pycache__/`),
  `README.md` (setup + run + caveat), `requirements.txt` (flask, croniter,
  pytest).
- Commit, then create a new GitHub repo via `gh` and push.
