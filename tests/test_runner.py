import subprocess
from auto_prompter.runner import build_command, run_job, _need_shell


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


def test_build_command_inherits_permission_mode_and_model():
    job = {
        "prompt": "hello",
        "target": {"type": "existing", "session_id": "sess1"},
        "settings": {
            "permission_mode": "bypassPermissions",
            "model": "claude-opus-4-8",
            "verbose": True,
        },
    }
    argv, _ = build_command(job, "/bin/claude")
    assert argv == [
        "/bin/claude", "--resume", "sess1", "-p", "hello",
        "--dangerously-skip-permissions", "--verbose",
        "--model", "claude-opus-4-8",
    ]


def test_run_job_success(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}
    calls = {}

    def fake_run(argv, cwd, stdout, stderr, text, shell=False, timeout=None):
        calls["argv"] = argv
        calls["cwd"] = cwd
        calls["timeout"] = timeout
        stdout.write("ok output")
        return subprocess.CompletedProcess(argv, 0)

    result = run_job(job, tmp_path, which=lambda _: "/bin/claude", run=fake_run)
    assert result["status"] == "done"
    assert calls["argv"] == ["/bin/claude", "-p", "hi"]
    assert calls["timeout"] == 3600
    assert "ok output" in (tmp_path / result["log_path"].split("/")[-1]).read_text()


def test_run_job_nonzero_is_failed(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}

    def fake_run(argv, cwd, stdout, stderr, text, shell=False, timeout=None):
        return subprocess.CompletedProcess(argv, 2)

    result = run_job(job, tmp_path, which=lambda _: "/bin/claude", run=fake_run)
    assert result["status"] == "failed"


def test_run_job_missing_binary_is_failed(tmp_path):
    job = {"id": "j1", "prompt": "hi", "target": {"type": "new", "folder": "/x"}}
    result = run_job(job, tmp_path, which=lambda _: None, run=None)
    assert result["status"] == "failed"
    assert "not found" in (tmp_path / result["log_path"].split("/")[-1]).read_text().lower()


def test_run_job_timeout_is_failed(tmp_path):
    job = {
        "id": "j1",
        "prompt": "hi",
        "target": {"type": "new", "folder": "/x"},
        "settings": {"timeout_seconds": 5},
    }

    def fake_run(argv, cwd, stdout, stderr, text, shell=False, timeout=None):
        raise subprocess.TimeoutExpired(argv, timeout)

    result = run_job(job, tmp_path, which=lambda _: "/bin/claude", run=fake_run)
    assert result["status"] == "failed"
    log = (tmp_path / result["log_path"].split("/")[-1]).read_text()
    assert "5-second timeout" in log


def test_run_job_uses_shell_for_windows_cmd(tmp_path, monkeypatch):
    # Test the _need_shell helper directly to avoid pathlib.WindowsPath issues
    # on non-Windows hosts when os.name is monkeypatched.
    assert _need_shell("C:\\tools\\claude.cmd", os_name="nt") is True
    assert _need_shell("C:\\tools\\claude.bat", os_name="nt") is True
    assert _need_shell("C:\\tools\\claude.exe", os_name="nt") is False


def test_run_job_no_shell_on_posix(tmp_path, monkeypatch):
    # Test the _need_shell helper: POSIX always returns False regardless of extension.
    assert _need_shell("/usr/bin/claude", os_name="posix") is False
    assert _need_shell("claude.cmd", os_name="posix") is False
