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
