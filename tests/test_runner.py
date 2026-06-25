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
