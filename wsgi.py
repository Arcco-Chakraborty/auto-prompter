# wsgi.py — gunicorn entry point.
#
# Run with ONE worker only: the app starts a background scheduler thread, and
# multiple workers would each run their own scheduler and double-fire jobs.
#   gunicorn -w 1 -b 127.0.0.1:5055 wsgi:app
from pathlib import Path

from app import create_app
from auto_prompter.service import Scheduler
from auto_prompter.store import JobStore

_base = Path(__file__).resolve().parent
_store = JobStore(_base / "jobs.json")
_logs_dir = _base / "logs"

_scheduler = Scheduler(_store, _logs_dir)
_scheduler.start()

app = create_app(_store, _logs_dir)
