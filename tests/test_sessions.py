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
