# app.py
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from auto_prompter import browse as browse_mod
from auto_prompter import sessions as sessions_mod
from auto_prompter.service import Scheduler, create_job
from auto_prompter.store import JobStore


def create_app(store, logs_dir):
    app = Flask(__name__)
    logs_dir = Path(logs_dir)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/sessions")
    def api_sessions():
        return jsonify(sessions_mod.discover_sessions())

    @app.get("/api/browse")
    def api_browse():
        return jsonify(browse_mod.list_dir(request.args.get("path") or None))

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(store.list())

    @app.post("/api/jobs")
    def api_create_job():
        data = request.get_json(force=True, silent=True) or {}
        job, err = create_job(store, data)
        if err:
            return jsonify({"error": err}), 400
        return jsonify(job), 201

    @app.delete("/api/jobs/<job_id>")
    def api_delete_job(job_id):
        if store.delete(job_id):
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @app.post("/api/jobs/<job_id>/toggle")
    def api_toggle_job(job_id):
        job = store.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        updated = store.update(job_id, enabled=not job.get("enabled", True))
        return jsonify(updated)

    @app.get("/api/jobs/<job_id>/log")
    def api_job_log(job_id):
        job = store.get(job_id)
        if not job or not job.get("last_log"):
            return jsonify({"error": "no log"}), 404
        try:
            text = Path(job["last_log"]).read_text(encoding="utf-8")
        except OSError:
            text = "(log file missing)"
        return jsonify({"log": text})

    return app


def main():
    base = Path(__file__).resolve().parent
    store = JobStore(base / "jobs.json")
    logs_dir = base / "logs"
    scheduler = Scheduler(store, logs_dir)
    scheduler.start()
    app = create_app(store, logs_dir)
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
