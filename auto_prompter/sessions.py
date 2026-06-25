import json
from pathlib import Path

NAME_MAX = 80
PERMISSION_MODES = {
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
}

# Prefixes that mark a "user" line as a slash command or local-command artifact
# rather than something a person typed as a chat message.
_SKIP_PREFIXES = ("<local-command-caveat>", "<command-name>")


def _default_dir():
    return Path.home() / ".claude" / "projects"


def _is_real_user_message(obj):
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    content = obj.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        return False
    if content.lstrip().startswith(_SKIP_PREFIXES):
        return False
    return True


def _parse_file(path):
    """Return the session's chat name, cwd, and reusable CLI settings.

    Name is Claude Code's generated ``aiTitle`` when present; otherwise the
    first real user message (skipping meta lines and slash commands). Claude's
    session log also records permission mode and model, which can be inherited
    when scheduling a resumed chat.
    """
    cwd = None
    ai_title = None
    first_msg = None
    permission_mode = None
    model = None
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
                if obj.get("type") == "ai-title" and isinstance(obj.get("aiTitle"), str):
                    ai_title = obj["aiTitle"].strip()
                elif first_msg is None and _is_real_user_message(obj):
                    first_msg = obj["message"]["content"].strip()
                candidate_mode = obj.get("permissionMode")
                if candidate_mode in PERMISSION_MODES:
                    permission_mode = candidate_mode
                message = obj.get("message")
                if isinstance(message, dict):
                    candidate_model = message.get("model")
                    if isinstance(candidate_model, str):
                        candidate_model = candidate_model.strip()
                        if candidate_model and not candidate_model.startswith("<"):
                            model = candidate_model
    except OSError:
        return None
    name = ai_title or first_msg or "(untitled chat)"
    settings = {}
    if permission_mode:
        settings["permission_mode"] = permission_mode
    if model:
        settings["model"] = model
    return {"cwd": cwd or "", "name": name[:NAME_MAX], "settings": settings}


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
            "name": parsed["name"],
            "settings": parsed["settings"],
            "last_used": jsonl.stat().st_mtime,
        })
    results.sort(key=lambda s: s["last_used"], reverse=True)
    return results
