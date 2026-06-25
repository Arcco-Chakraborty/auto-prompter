import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def _need_shell(claude_path, os_name=None):
    """Return True only on Windows when claude_path is a .cmd/.bat shim."""
    if os_name is None:
        os_name = os.name
    return os_name == "nt" and claude_path.lower().endswith((".cmd", ".bat"))


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
            proc = run(argv, cwd=cwd, stdout=out, stderr=out, text=True, shell=_need_shell(claude_path))
            status = "done" if proc.returncode == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 - record any launch failure
            out.write(f"\nERROR launching claude: {exc}\n")
            status = "failed"
    return {"status": status, "log_path": str(log_file), "ran_at": ran_at}
