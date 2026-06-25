# Auto Prompter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask web app that sends user-specified prompts to the `claude` CLI at scheduled times (one-time or recurring), targeting a new chat in a chosen folder or an existing discovered chat.

**Architecture:** A single Python process runs a Flask server (UI + JSON API) plus a background scheduler thread that wakes every ~15s and fires due jobs by running `claude -p` headlessly. Jobs persist to `jobs.json`; run output goes to per-run files under `logs/`. Sessions are discovered by scanning `~/.claude/projects/*/*.jsonl`.

**Tech Stack:** Python 3.9+, Flask, croniter, pytest. Standard library: `pathlib`, `subprocess`, `shutil`, `json`, `threading`, `uuid`, `datetime`.

## Global Constraints

- Cross-platform: Linux, macOS, **Windows**. No tmux, no shell-isms. Use `pathlib`/`Path.home()` and `shutil.which("claude")` (resolves `claude.cmd` on Windows).
- Prompt delivery is **headless only**: `claude -p "<prompt>"` (new) or `claude --resume <session_id> -p "<prompt>"` (existing). Never parse Claude's answer.
- Scheduler is **in-process** (no OS cron / Task Scheduler). Prompts fire only while `app.py` runs.
- Sessions path: `Path.home() / ".claude" / "projects"`.
- Persistence file: `jobs.json`. Run logs: `logs/<id>-<timestamp>.log`. Atomic writes (temp file + `os.replace`).
- Default UI: `http://localhost:5000`. Repo name `auto-prompter`, **private**.
- All `claude` subprocess calls are mocked in tests — never invoke the real CLI in a test.
- TDD throughout. Commit after each task.

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `README.md`
- Create: `auto_prompter/__init__.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: nothing.
- Produces: the `auto_prompter` package importable as `auto_prompter`; pytest runnable via `pytest`.

- [ ] **Step 1: Create `requirements.txt`**

```
flask==3.0.3
croniter==2.0.5
pytest==8.2.0
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
venv/
.venv/
jobs.json
logs/
.pytest_cache/
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 4: Create empty package files**

Create `auto_prompter/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 5: Create `README.md`**

```markdown
# Auto Prompter

Sends prompts to the `claude` CLI on a schedule (one-time or recurring),
targeting a new chat in a chosen folder or an existing discovered chat.
Cross-platform (Linux/macOS/Windows). No answer-parsing — it only sends.

## Requirements
- Python 3.9+
- The `claude` CLI installed and on PATH (`claude --version` should work)

## Setup
```bash
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
python app.py
```
Open http://localhost:5000.

**Note:** prompts fire only while `python app.py` is running.

## Tests
```bash
pytest
```
```

- [ ] **Step 6: Install deps and verify pytest runs**

Run: `pip install -r requirements.txt && pytest`
Expected: pytest runs and reports "no tests ran" (exit 5) — confirms install works.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore README.md pytest.ini auto_prompter/__init__.py tests/__init__.py
git commit -m "chore: scaffold auto-prompter project"
```

---

### Task 2: Job store (`store.py`)

**Files:**
- Create: `auto_prompter/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class JobStore(path: pathlib.Path)`
  - `JobStore.list() -> list[dict]`
  - `JobStore.get(job_id: str) -> dict | None`
  - `JobStore.add(job: dict) -> dict` (returns stored job)
  - `JobStore.update(job_id: str, **fields) -> dict | None`
  - `JobStore.delete(job_id: str) -> bool`
  - Jobs are plain dicts with at least the keys defined in the spec data model.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_store.py
from auto_prompter.store import JobStore

def test_add_and_list(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job = store.add({"id": "a", "prompt": "hi", "enabled": True})
    assert job["id"] == "a"
    assert store.list() == [job]

def test_get(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a", "prompt": "hi"})
    assert store.get("a")["prompt"] == "hi"
    assert store.get("missing") is None

def test_update(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a", "prompt": "hi", "status": "pending"})
    updated = store.update("a", status="done")
    assert updated["status"] == "done"
    assert store.get("a")["status"] == "done"
    assert store.update("missing", status="x") is None

def test_delete(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a"})
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.list() == []

def test_persists_across_instances(tmp_path):
    path = tmp_path / "jobs.json"
    JobStore(path).add({"id": "a", "prompt": "hi"})
    assert JobStore(path).get("a")["prompt"] == "hi"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auto_prompter.store'`.

- [ ] **Step 3: Implement `store.py`**

```python
# auto_prompter/store.py
import json
import os
import threading
from pathlib import Path


class JobStore:
    """Thread-safe CRUD over a JSON file holding a list of job dicts."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self):
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, jobs):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)
        os.replace(tmp, self.path)

    def list(self):
        with self._lock:
            return self._read()

    def get(self, job_id):
        for job in self._read():
            if job.get("id") == job_id:
                return job
        return None

    def add(self, job):
        with self._lock:
            jobs = self._read()
            jobs.append(job)
            self._write(jobs)
            return job

    def update(self, job_id, **fields):
        with self._lock:
            jobs = self._read()
            for job in jobs:
                if job.get("id") == job_id:
                    job.update(fields)
                    self._write(jobs)
                    return job
            return None

    def delete(self, job_id):
        with self._lock:
            jobs = self._read()
            new_jobs = [j for j in jobs if j.get("id") != job_id]
            if len(new_jobs) == len(jobs):
                return False
            self._write(new_jobs)
            return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/store.py tests/test_store.py
git commit -m "feat: add JobStore JSON persistence"
```

---

### Task 3: Session discovery (`sessions.py`)

**Files:**
- Create: `auto_prompter/sessions.py`
- Test: `tests/test_sessions.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `discover_sessions(projects_dir: pathlib.Path | None = None) -> list[dict]`
    where each dict is `{"session_id": str, "cwd": str, "label": str, "last_used": float}`, sorted by `last_used` descending. Defaults to `Path.home()/".claude"/"projects"`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sessions.py
import json
from auto_prompter.sessions import discover_sessions


def _write_session(projects_dir, encoded, session_id, lines):
    d = projects_dir / encoded
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{session_id}.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    return f


def test_extracts_cwd_and_first_real_user_message(tmp_path):
    _write_session(tmp_path, "-home-me-proj", "sess1", [
        {"type": "last-prompt", "sessionId": "sess1"},
        {"type": "user", "isMeta": True,
         "message": {"role": "user",
                     "content": "<local-command-caveat>x</local-command-caveat>"}},
        {"type": "user", "cwd": "/home/me/proj",
         "message": {"role": "user", "content": "Fix the parser bug please"}},
    ])
    sessions = discover_sessions(tmp_path)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_id"] == "sess1"
    assert s["cwd"] == "/home/me/proj"
    assert s["label"] == "Fix the parser bug please"


def test_sorted_by_last_used_desc(tmp_path):
    import os, time
    f1 = _write_session(tmp_path, "-a", "old", [
        {"type": "user", "cwd": "/a", "message": {"role": "user", "content": "a"}}])
    f2 = _write_session(tmp_path, "-b", "new", [
        {"type": "user", "cwd": "/b", "message": {"role": "user", "content": "b"}}])
    os.utime(f1, (1000, 1000))
    os.utime(f2, (2000, 2000))
    ids = [s["session_id"] for s in discover_sessions(tmp_path)]
    assert ids == ["new", "old"]


def test_skips_non_session_files_and_missing_dir(tmp_path):
    (tmp_path / "-a").mkdir(parents=True)
    (tmp_path / "-a" / "memory").mkdir()
    (tmp_path / "-a" / "notes.txt").write_text("ignore me")
    assert discover_sessions(tmp_path) == []
    assert discover_sessions(tmp_path / "does-not-exist") == []


def test_label_truncated(tmp_path):
    long = "x" * 200
    _write_session(tmp_path, "-a", "s", [
        {"type": "user", "cwd": "/a", "message": {"role": "user", "content": long}}])
    label = discover_sessions(tmp_path)[0]["label"]
    assert len(label) <= 80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sessions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auto_prompter.sessions'`.

- [ ] **Step 3: Implement `sessions.py`**

```python
# auto_prompter/sessions.py
import json
from pathlib import Path

LABEL_MAX = 80


def _default_dir():
    return Path.home() / ".claude" / "projects"


def _is_real_user_message(obj):
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    content = obj.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        return False
    if content.lstrip().startswith("<local-command-caveat>"):
        return False
    return True


def _parse_file(path):
    cwd = None
    label = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cwd is None and isinstance(obj.get("cwd"), str):
                    cwd = obj["cwd"]
                if label is None and _is_real_user_message(obj):
                    label = obj["message"]["content"].strip()[:LABEL_MAX]
                if cwd and label:
                    break
    except OSError:
        return None
    return {"cwd": cwd or "", "label": label or "(no message)"}


def discover_sessions(projects_dir=None):
    base = Path(projects_dir) if projects_dir else _default_dir()
    if not base.exists():
        return []
    results = []
    for jsonl in base.glob("*/*.jsonl"):
        parsed = _parse_file(jsonl)
        if parsed is None:
            continue
        results.append({
            "session_id": jsonl.stem,
            "cwd": parsed["cwd"],
            "label": parsed["label"],
            "last_used": jsonl.stat().st_mtime,
        })
    results.sort(key=lambda s: s["last_used"], reverse=True)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sessions.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/sessions.py tests/test_sessions.py
git commit -m "feat: add Claude session discovery"
```

---

### Task 4: Command runner (`runner.py`)

**Files:**
- Create: `auto_prompter/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: a job dict (from `store`), with `target` per the spec data model.
- Produces:
  - `build_command(job: dict, claude_path: str) -> tuple[list[str], str]` returning `(argv, cwd)`.
  - `run_job(job: dict, logs_dir: pathlib.Path, which=shutil.which, run=subprocess.run) -> dict` returning `{"status": "done"|"failed", "log_path": str, "ran_at": str}`. `which`/`run` are injectable for tests.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_runner.py
import subprocess
from auto_prompter.runner import build_command, run_job


def test_build_command_new_chat():
    job = {"prompt": "hello", "target": {"type": "new", "folder": "/work/dir"}}
    argv, cwd = build_command(job, "/bin/claude")
    assert argv == ["/bin/claude", "-p", "hello"]
    assert cwd == "/work/dir"


def test_build_command_existing_chat():
    job = {"prompt": "hello", "target": {
        "type": "existing", "session_id": "sess1", "session_folder": "/work/dir"}}
    argv, cwd = build_command(job, "/bin/claude")
    assert argv == ["/bin/claude", "--resume", "sess1", "-p", "hello"]
    assert cwd == "/work/dir"


def test_run_job_success(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}
    calls = {}

    def fake_run(argv, cwd, stdout, stderr, text):
        calls["argv"] = argv
        calls["cwd"] = cwd
        stdout.write("ok output")
        return subprocess.CompletedProcess(argv, 0)

    result = run_job(job, tmp_path, which=lambda _: "/bin/claude", run=fake_run)
    assert result["status"] == "done"
    assert calls["argv"] == ["/bin/claude", "-p", "hi"]
    assert "ok output" in (tmp_path / result["log_path"].split("/")[-1]).read_text()


def test_run_job_nonzero_is_failed(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}

    def fake_run(argv, cwd, stdout, stderr, text):
        return subprocess.CompletedProcess(argv, 2)

    result = run_job(job, tmp_path, which=lambda _: "/bin/claude", run=fake_run)
    assert result["status"] == "failed"


def test_run_job_missing_binary_is_failed(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}
    result = run_job(job, tmp_path, which=lambda _: None, run=None)
    assert result["status"] == "failed"
    assert "not found" in (tmp_path / result["log_path"].split("/")[-1]).read_text().lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auto_prompter.runner'`.

- [ ] **Step 3: Implement `runner.py`**

```python
# auto_prompter/runner.py
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def build_command(job, claude_path):
    target = job["target"]
    prompt = job["prompt"]
    if target["type"] == "existing":
        argv = [claude_path, "--resume", target["session_id"], "-p", prompt]
        cwd = target.get("session_folder") or None
    else:
        argv = [claude_path, "-p", prompt]
        cwd = target.get("folder") or None
    return argv, cwd


def run_job(job, logs_dir, which=shutil.which, run=subprocess.run):
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    ran_at = datetime.now().isoformat(timespec="seconds")
    stamp = ran_at.replace(":", "").replace("-", "")
    log_file = logs_dir / f"{job['id']}-{stamp}.log"

    claude_path = which("claude")
    if not claude_path:
        log_file.write_text("ERROR: 'claude' binary not found on PATH.\n",
                            encoding="utf-8")
        return {"status": "failed", "log_path": str(log_file), "ran_at": ran_at}

    argv, cwd = build_command(job, claude_path)
    with log_file.open("w", encoding="utf-8") as out:
        out.write(f"$ {' '.join(argv)}  (cwd={cwd})\n\n")
        out.flush()
        try:
            proc = run(argv, cwd=cwd, stdout=out, stderr=out, text=True)
            status = "done" if proc.returncode == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 - record any launch failure
            out.write(f"\nERROR launching claude: {exc}\n")
            status = "failed"
    return {"status": status, "log_path": str(log_file), "ran_at": ran_at}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/runner.py tests/test_runner.py
git commit -m "feat: add claude command runner"
```

---

### Task 5: Scheduling logic (`schedule.py`)

**Files:**
- Create: `auto_prompter/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Consumes: a job dict with `schedule` per spec; `croniter`.
- Produces:
  - `next_run_at(job: dict, after: datetime) -> datetime | None` — for `once` returns `run_at` (parsed) if `status != "done"` else None; for `recurring` returns next cron time strictly after `after`.
  - `is_due(job: dict, now: datetime) -> bool` — True when enabled and due.
  - `validate_schedule(schedule: dict) -> str | None` — returns an error message or None.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_schedule.py
from datetime import datetime
from auto_prompter.schedule import next_run_at, is_due, validate_schedule


def test_once_due_when_past():
    job = {"enabled": True, "status": "pending",
           "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 10, 0, 1)) is True
    assert is_due(job, datetime(2026, 6, 25, 9, 59, 0)) is False


def test_once_not_due_when_done():
    job = {"enabled": True, "status": "done",
           "schedule": {"type": "once", "run_at": "2026-06-25T10:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 11, 0, 0)) is False


def test_disabled_never_due():
    job = {"enabled": False, "status": "pending",
           "schedule": {"type": "once", "run_at": "2020-01-01T00:00:00"}}
    assert is_due(job, datetime(2026, 6, 25, 11, 0, 0)) is False


def test_recurring_next_run_strictly_after():
    job = {"enabled": True, "status": "pending",
           "schedule": {"type": "recurring", "cron": "0 9 * * *"}}
    nxt = next_run_at(job, datetime(2026, 6, 25, 9, 0, 0))
    assert nxt == datetime(2026, 6, 26, 9, 0, 0)


def test_recurring_due_uses_next_run_at_field():
    job = {"enabled": True, "status": "pending",
           "next_run_at": "2026-06-25T09:00:00",
           "schedule": {"type": "recurring", "cron": "0 9 * * *"}}
    assert is_due(job, datetime(2026, 6, 25, 9, 0, 1)) is True
    assert is_due(job, datetime(2026, 6, 25, 8, 59, 0)) is False


def test_validate_schedule():
    assert validate_schedule({"type": "recurring", "cron": "0 9 * * *"}) is None
    assert validate_schedule({"type": "recurring", "cron": "not a cron"}) is not None
    assert validate_schedule({"type": "once", "run_at": "2026-06-25T10:00:00"}) is None
    assert validate_schedule({"type": "once", "run_at": "nonsense"}) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schedule.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auto_prompter.schedule'`.

- [ ] **Step 3: Implement `schedule.py`**

```python
# auto_prompter/schedule.py
from datetime import datetime
from croniter import croniter


def _parse_dt(value):
    return datetime.fromisoformat(value)


def next_run_at(job, after):
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") == "done":
            return None
        return _parse_dt(sched["run_at"])
    return croniter(sched["cron"], after).get_next(datetime)


def is_due(job, now):
    if not job.get("enabled", True):
        return False
    sched = job["schedule"]
    if sched["type"] == "once":
        if job.get("status") == "done":
            return False
        return now >= _parse_dt(sched["run_at"])
    # recurring: rely on precomputed next_run_at; if absent, compute from cron
    nxt = job.get("next_run_at")
    target = _parse_dt(nxt) if nxt else croniter(
        sched["cron"], now).get_prev(datetime)
    return now >= target


def validate_schedule(schedule):
    stype = schedule.get("type")
    if stype == "once":
        try:
            _parse_dt(schedule["run_at"])
        except (ValueError, KeyError, TypeError):
            return "Invalid one-time date/time."
        return None
    if stype == "recurring":
        try:
            croniter(schedule["cron"])
        except (ValueError, KeyError, TypeError):
            return "Invalid cron expression."
        return None
    return "Unknown schedule type."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schedule.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/schedule.py tests/test_schedule.py
git commit -m "feat: add scheduling logic (once + cron)"
```

---

### Task 6: Job service + scheduler thread (`service.py`)

**Files:**
- Create: `auto_prompter/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `JobStore`, `schedule.is_due`, `schedule.next_run_at`, `schedule.validate_schedule`, `runner.run_job`.
- Produces:
  - `create_job(store, data: dict) -> tuple[dict | None, str | None]` — validates, assigns `id`/defaults, computes initial `next_run_at`, persists. Returns `(job, None)` or `(None, error)`.
  - `tick(store, logs_dir, now, run_job=runner.run_job) -> list[str]` — fires all due jobs once, updates their status/`last_run_at`/`last_log`/`next_run_at`. Returns list of fired job ids.
  - `class Scheduler(store, logs_dir, interval=15)` with `start()` and `stop()` running `tick` in a daemon thread.

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auto_prompter.service'`.

- [ ] **Step 3: Implement `service.py`**

```python
# auto_prompter/service.py
import threading
import time
import uuid
from datetime import datetime

from . import runner
from .schedule import is_due, next_run_at, validate_schedule


def create_job(store, data):
    schedule = data.get("schedule", {})
    err = validate_schedule(schedule)
    if err:
        return None, err
    if not data.get("prompt", "").strip():
        return None, "Prompt is required."
    target = data.get("target", {})
    if target.get("type") not in ("new", "existing"):
        return None, "Invalid target."

    job = {
        "id": uuid.uuid4().hex,
        "prompt": data["prompt"],
        "target": target,
        "schedule": schedule,
        "enabled": True,
        "status": "pending",
        "last_run_at": None,
        "last_log": None,
        "next_run_at": None,
    }
    nxt = next_run_at(job, datetime.now())
    job["next_run_at"] = nxt.isoformat(timespec="seconds") if nxt else None
    store.add(job)
    return job, None


def tick(store, logs_dir, now, run_job=runner.run_job):
    fired = []
    for job in store.list():
        if not is_due(job, now):
            continue
        result = run_job(job, logs_dir)
        fields = {
            "last_run_at": result["ran_at"],
            "last_log": result["log_path"],
        }
        if job["schedule"]["type"] == "once":
            fields["status"] = result["status"]
            fields["next_run_at"] = None
        else:
            fields["status"] = result["status"]
            nxt = next_run_at(job, now)
            fields["next_run_at"] = nxt.isoformat(timespec="seconds")
        store.update(job["id"], **fields)
        fired.append(job["id"])
    return fired


class Scheduler:
    def __init__(self, store, logs_dir, interval=15):
        self.store = store
        self.logs_dir = logs_dir
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                tick(self.store, self.logs_dir, datetime.now())
            except Exception:  # noqa: BLE001 - never let the loop die
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add auto_prompter/service.py tests/test_service.py
git commit -m "feat: add job service and scheduler thread"
```

---

### Task 7: Flask app + API (`app.py`)

**Files:**
- Create: `app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `JobStore`, `service.create_job`, `sessions.discover_sessions`, `service.Scheduler`.
- Produces: a Flask `create_app(store, logs_dir)` factory plus the API routes from the spec. `app.py` run directly starts the scheduler and `app.run(port=5000)`.

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `app.py`**

```python
# app.py
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from auto_prompter import sessions as sessions_mod
from auto_prompter.service import Scheduler, create_job
from auto_prompter.store import JobStore


def create_app(store, logs_dir):
    app = Flask(__name__)
    logs_dir = Path(logs_dir)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/sessions")
    def api_sessions():
        return jsonify(sessions_mod.discover_sessions())

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(store.list())

    @app.post("/api/jobs")
    def api_create_job():
        data = request.get_json(force=True, silent=True) or {}
        job, err = create_job(store, data)
        if err:
            return jsonify({"error": err}), 400
        return jsonify(job), 201

    @app.delete("/api/jobs/<job_id>")
    def api_delete_job(job_id):
        if store.delete(job_id):
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @app.post("/api/jobs/<job_id>/toggle")
    def api_toggle_job(job_id):
        job = store.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        updated = store.update(job_id, enabled=not job.get("enabled", True))
        return jsonify(updated)

    @app.get("/api/jobs/<job_id>/log")
    def api_job_log(job_id):
        job = store.get(job_id)
        if not job or not job.get("last_log"):
            return jsonify({"error": "no log"}), 404
        try:
            text = Path(job["last_log"]).read_text(encoding="utf-8")
        except OSError:
            text = "(log file missing)"
        return jsonify({"log": text})

    return app


def main():
    base = Path(__file__).resolve().parent
    store = JobStore(base / "jobs.json")
    logs_dir = base / "logs"
    scheduler = Scheduler(store, logs_dir)
    scheduler.start()
    app = create_app(store, logs_dir)
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create minimal `templates/index.html` so the index test passes**

Create `templates/index.html` with at least a title containing "Auto Prompter" (full UI comes in Task 8):

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Auto Prompter</title></head>
<body><h1>Auto Prompter</h1></body>
</html>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py templates/index.html
git commit -m "feat: add Flask app and JSON API"
```

---

### Task 8: Web UI (`templates/index.html` + `static/`)

**Files:**
- Modify: `templates/index.html` (replace placeholder with full UI)
- Create: `static/app.js`
- Create: `static/style.css`

**Interfaces:**
- Consumes: the JSON API from Task 7 (`/api/sessions`, `/api/jobs`, POST/DELETE/toggle, `/api/jobs/<id>/log`).
- Produces: the browser UI. No new tests (covered by API tests + manual run); this task is UI markup/JS.

- [ ] **Step 1: Replace `templates/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Prompter</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <h1>Auto Prompter</h1>
  <p class="note">Prompts fire only while <code>python app.py</code> is running.</p>

  <section class="card">
    <h2>New scheduled prompt</h2>
    <form id="job-form">
      <label>Prompt
        <textarea name="prompt" rows="3" required></textarea>
      </label>

      <fieldset>
        <legend>Target</legend>
        <label><input type="radio" name="target_type" value="new" checked> New chat in folder</label>
        <input type="text" name="folder" placeholder="/absolute/path/to/project">
        <label><input type="radio" name="target_type" value="existing"> Existing chat</label>
        <select name="session"></select>
        <button type="button" id="refresh-sessions">Refresh chats</button>
      </fieldset>

      <fieldset>
        <legend>Schedule</legend>
        <label><input type="radio" name="sched_type" value="once" checked> One-time</label>
        <input type="datetime-local" name="run_at">
        <label><input type="radio" name="sched_type" value="recurring"> Recurring</label>
        <select id="cron-preset">
          <option value="">— preset —</option>
          <option value="0 9 * * *">Every day at 09:00</option>
          <option value="0 * * * *">Every hour</option>
          <option value="*/30 * * * *">Every 30 minutes</option>
          <option value="0 9 * * 1">Every Monday at 09:00</option>
        </select>
        <input type="text" name="cron" placeholder="raw cron e.g. 0 9 * * *">
      </fieldset>

      <button type="submit">Schedule prompt</button>
      <span id="form-error" class="error"></span>
    </form>
  </section>

  <section class="card">
    <h2>Scheduled prompts</h2>
    <table id="jobs-table">
      <thead><tr><th>Prompt</th><th>Target</th><th>Next run</th><th>Status</th><th>Last run</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
  </section>

  <section class="card">
    <h2>Existing chats</h2>
    <ul id="sessions-list"></ul>
  </section>

  <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Create `static/style.css`**

```css
body { font-family: system-ui, sans-serif; max-width: 880px; margin: 2rem auto; padding: 0 1rem; color: #1c1c1c; }
h1 { margin-bottom: .25rem; }
.note { color: #666; margin-top: 0; }
.card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0; }
label { display: block; margin: .5rem 0 .25rem; }
textarea, input[type=text], select, input[type=datetime-local] { width: 100%; max-width: 480px; padding: .4rem; box-sizing: border-box; }
fieldset { margin: .75rem 0; }
button { padding: .45rem .9rem; margin-top: .5rem; cursor: pointer; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; border-bottom: 1px solid #eee; padding: .4rem; font-size: .9rem; vertical-align: top; }
.error { color: #b00020; margin-left: .5rem; }
.status-done { color: #0a7; } .status-failed { color: #b00020; } .status-pending { color: #888; }
#sessions-list li { margin: .35rem 0; font-size: .9rem; }
.muted { color: #888; }
```

- [ ] **Step 3: Create `static/app.js`**

```javascript
async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function fmt(dt) { return dt ? dt.replace("T", " ") : "—"; }

async function loadSessions() {
  const { data } = await fetchJSON("/api/sessions");
  const select = document.querySelector("select[name=session]");
  const list = document.getElementById("sessions-list");
  select.innerHTML = "";
  list.innerHTML = "";
  data.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = JSON.stringify({ id: s.session_id, folder: s.cwd });
    opt.textContent = `${s.label}  —  ${s.cwd}`;
    select.appendChild(opt);

    const li = document.createElement("li");
    li.innerHTML = `<strong>${s.label}</strong><br><span class="muted">${s.cwd} · ${s.session_id}</span>`;
    list.appendChild(li);
  });
}

async function loadJobs() {
  const { data } = await fetchJSON("/api/jobs");
  const tbody = document.querySelector("#jobs-table tbody");
  tbody.innerHTML = "";
  data.forEach((j) => {
    const tr = document.createElement("tr");
    const target = j.target.type === "new"
      ? `new · ${j.target.folder || ""}`
      : `resume · ${j.target.session_id}`;
    tr.innerHTML = `
      <td>${(j.prompt || "").slice(0, 60)}</td>
      <td>${target}</td>
      <td>${fmt(j.next_run_at)}</td>
      <td class="status-${j.status}">${j.enabled ? j.status : "disabled"}</td>
      <td>${fmt(j.last_run_at)}</td>
      <td>
        <button data-act="toggle" data-id="${j.id}">${j.enabled ? "Disable" : "Enable"}</button>
        <button data-act="log" data-id="${j.id}">Log</button>
        <button data-act="delete" data-id="${j.id}">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
}

document.querySelector("#jobs-table").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const { act, id } = btn.dataset;
  if (act === "delete") await fetchJSON(`/api/jobs/${id}`, { method: "DELETE" });
  else if (act === "toggle") await fetchJSON(`/api/jobs/${id}/toggle`, { method: "POST" });
  else if (act === "log") {
    const { data } = await fetchJSON(`/api/jobs/${id}/log`);
    alert(data.log || data.error || "no log");
    return;
  }
  loadJobs();
});

document.getElementById("refresh-sessions").addEventListener("click", loadSessions);

document.getElementById("cron-preset").addEventListener("change", (e) => {
  if (e.target.value) document.querySelector("input[name=cron]").value = e.target.value;
});

document.getElementById("job-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const errEl = document.getElementById("form-error");
  errEl.textContent = "";

  const targetType = f.target_type.value;
  let target;
  if (targetType === "existing") {
    const sel = f.session.value;
    if (!sel) { errEl.textContent = "Pick an existing chat or refresh the list."; return; }
    const { id, folder } = JSON.parse(sel);
    target = { type: "existing", session_id: id, session_folder: folder };
  } else {
    target = { type: "new", folder: f.folder.value.trim() };
  }

  const schedType = f.sched_type.value;
  const schedule = schedType === "once"
    ? { type: "once", run_at: f.run_at.value }
    : { type: "recurring", cron: f.cron.value.trim() };

  const { ok, data } = await fetchJSON("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: f.prompt.value, target, schedule }),
  });
  if (!ok) { errEl.textContent = data.error || "Failed to schedule."; return; }
  f.reset();
  loadJobs();
});

loadSessions();
loadJobs();
setInterval(loadJobs, 10000);
```

- [ ] **Step 4: Manual smoke test**

Run: `python app.py`, open http://localhost:5000. Verify the form, jobs table, and existing-chats list render and that adding a one-time prompt a minute in the future creates a row. (Optional: let it fire and check `logs/`.)

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 2–7).

- [ ] **Step 6: Commit**

```bash
git add templates/index.html static/app.js static/style.css
git commit -m "feat: add web UI"
```

---

### Task 9: Push to GitHub

**Files:** none (repo operation).

**Interfaces:** Consumes the committed repo. Produces a private GitHub repo `auto-prompter` with `main` pushed.

- [ ] **Step 1: Confirm clean tree and tests green**

Run: `pytest -q && git status --short`
Expected: tests pass; `git status` shows nothing to commit.

- [ ] **Step 2: Ensure branch is `main`**

Run: `git branch -M main`

- [ ] **Step 3: Create the private repo and push**

Run: `gh repo create auto-prompter --private --source=. --remote=origin --push`
Expected: repo created under `Arcco-Chakraborty`, `main` pushed, prints the repo URL.

- [ ] **Step 4: Verify**

Run: `gh repo view --web` (or `git remote -v`)
Expected: remote `origin` points at `github.com/Arcco-Chakraborty/auto-prompter`.

---

## Notes for the implementer

- Run `pytest` after every task; keep it green.
- The `.gitignore` excludes `jobs.json` and `logs/` — never commit runtime state.
- `jobs.json` and `logs/` are created at runtime next to `app.py`.
- Windows: `gh` and `git` commands are identical; activate the venv with `venv\Scripts\activate`.
