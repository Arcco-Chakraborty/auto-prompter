# Auto Prompter

A small local web app that **sends prompts to the `claude` CLI on a schedule**.
Each scheduled prompt either starts a **new** Claude Code chat in a folder you
pick, or **resumes an existing** chat selected from a list of your past
sessions. It runs the prompt headlessly (`claude -p "…"`) and does **not** read
or react to Claude's answers — it only sends.

Cross-platform: Linux, macOS, and Windows.

## Features

- **Web UI** at `http://localhost:5000` — no terminal juggling.
- **One-time** prompts (fire at a specific date & time) and **recurring**
  prompts (cron expression, with handy presets).
- **New chat** in a folder you choose, with a built-in **folder browser** so you
  can click through directories instead of typing a path.
- **Existing chat** targeting — auto-discovers your past Claude Code sessions and
  lists them by their generated **chat name** and **last-used time**.
- **Session setting inheritance** — resumed chats can auto-fill their recorded
  permission mode and model, with editable overrides before scheduling.
- **All local drives** in the folder browser on Windows, plus visible Close,
  Cancel, and Escape-key dismissal.
- **Jobs dashboard** — see next-run time, status, last run, view captured
  output, and enable/disable or delete any job.

## Requirements

- **Python 3.9+** — check with `python --version`.
- **The `claude` CLI** installed and on your PATH — check with
  `claude --version`. (Install: https://docs.claude.com/en/docs/claude-code )

## Setup

Clone the repo, then create a virtual environment and install dependencies.

### Windows (PowerShell)

```powershell
git clone https://github.com/Arcco-Chakraborty/auto-prompter.git
cd auto-prompter
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks the activate script, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that
> window, then re-run the activate line. (Or use **Command Prompt** instead:
> `venv\Scripts\activate.bat`.)

### Linux / macOS

```bash
git clone https://github.com/Arcco-Chakraborty/auto-prompter.git
cd auto-prompter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

With the virtual environment activated:

```bash
python app.py
```

Then open **http://localhost:5000** in your browser.

> **Important:** prompts only fire while `python app.py` is running. Leave the
> window open (or run it in a background terminal) for scheduled prompts to go
> out. There is no OS-level scheduler — this keeps behavior identical on every
> platform.

## Using it

1. **Write your prompt** in the text box.
2. **Pick a target:**
   - *New chat in folder* — type a path or click **Browse…** to pick a folder.
   - *Existing chat* — choose one from the dropdown (refresh the list if you
     just used Claude Code).
3. **Review Claude CLI settings.** For an existing chat, the app detects and
   auto-fills the session's recorded permission mode and model. You can disable
   auto-fill or edit either setting. Verbose mode, extra flags, and a run
   timeout are also available.
4. **Pick a schedule:**
   - *One-time* — choose a date and time.
   - *Recurring* — pick a preset (e.g. "Every day at 09:00") or type a raw cron
      expression like `0 9 * * *`.
5. Click **Schedule prompt**. It appears in the jobs table and fires at its time.

Captured output for each run is saved under `logs/` and viewable from the
**Log** button on each job.

## How it works

- A single Python process runs a **Flask web server** plus a **background
  scheduler thread** that wakes every ~15 seconds and dispatches due jobs in
  independent worker threads.
- Jobs are stored in `jobs.json` (created next to `app.py` at runtime).
- Existing chats are discovered by reading Claude Code's session files under
  `~/.claude/projects/` (`%USERPROFILE%\.claude\projects` on Windows).
- New chats run `claude -p "<prompt>"` in the chosen folder; existing chats run
  `claude --resume <session-id> -p "<prompt>"`.

`jobs.json` and `logs/` hold your local runtime state and are git-ignored.

## Tests

```bash
pytest
```

## Notes & limitations

- Fires only while the app is running (see above).
- It sends prompts; it does not read Claude's replies or act on them.
- Failed one-time jobs are terminal and do not retry automatically. Recurring
  jobs remain scheduled after a failed run.
- Each Claude run has a configurable timeout (one hour by default).
- One-time schedules are stored as UTC, while recurring cron schedules retain
  the browser's IANA timezone for daylight-saving-safe calculation.
- The Windows `.cmd` launch path is implemented (Claude's CLI shim is launched
  via the shell on Windows) but was developed on Linux — if a scheduled run
  fails on Windows, check the job's **Log** for the captured error.
