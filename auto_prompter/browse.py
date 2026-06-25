"""Filesystem directory browsing for the in-app folder picker.

This tool runs locally, so the server browses the user's own machine and
returns absolute paths the `claude` CLI can use as a working directory.
"""
import platform
import string
from pathlib import Path


def list_drives():
    """Return available filesystem roots (drive letters on Windows, / on POSIX)."""
    if platform.system() == "Windows":
        drives = []
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:\\")
            try:
                if root.exists():
                    drives.append({"name": f"{letter}:\\", "path": f"{letter}:\\"})
            except OSError:
                continue
        return drives
    return [{"name": "/", "path": "/"}]


def list_dir(path=None):
    """List sub-directories of ``path`` (defaults to the user's home).

    Returns a dict with the resolved absolute ``path``, its ``parent``
    (absolute path string, or None at the filesystem root), and ``dirs`` —
    a list of ``{"name", "path"}`` for each visible sub-directory, with
    absolute child paths computed server-side (no client path joining).
    Hidden (dot) directories are omitted. Unreadable/invalid paths fall
    back to home.
    """
    try:
        base = Path(path).expanduser() if path else Path.home()
        base = base.resolve()
        if not base.is_dir():
            base = Path.home().resolve()
    except (OSError, RuntimeError):
        base = Path.home().resolve()

    dirs = []
    try:
        for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
            except OSError:
                continue
    except (PermissionError, OSError):
        pass

    parent = None if base.parent == base else str(base.parent)
    return {"path": str(base), "parent": parent, "dirs": dirs, "drives": list_drives()}
