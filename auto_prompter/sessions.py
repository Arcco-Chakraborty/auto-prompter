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
