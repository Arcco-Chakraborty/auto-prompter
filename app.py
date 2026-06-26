# app.py
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from auto_prompter import auth as auth_mod
from auto_prompter import browse as browse_mod
from auto_prompter import sessions as sessions_mod
from auto_prompter.service import Scheduler, create_job
from auto_prompter.store import JobStore


def _is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def create_app(store, logs_dir):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("AUTO_PROMPTER_HTTPS") == "1",
    )
    # This is a local development-style app. Keep templates and static assets
    # in sync while it is running so editing one cannot leave the browser with
    # old HTML and new JavaScript.
    app.config.update(
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    logs_dir = Path(logs_dir).resolve()

    @app.get("/")
    @auth_mod.login_required
    def index():
        return render_template("index.html")

    @app.get("/api/sessions")
    @auth_mod.login_required
    def api_sessions():
        return jsonify(sessions_mod.discover_sessions())

    @app.get("/api/browse")
    @auth_mod.login_required
    def api_browse():
        return jsonify(browse_mod.list_dir(request.args.get("path") or None))

    @app.get("/api/jobs")
    @auth_mod.login_required
    def api_jobs():
        return jsonify(store.list())

    @app.post("/api/jobs")
    @auth_mod.login_required
    def api_create_job():
        data = request.get_json(force=True, silent=True) or {}
        job, err = create_job(store, data)
        if err:
            return jsonify({"error": err}), 400
        return jsonify(job), 201

    @app.delete("/api/jobs/<job_id>")
    @auth_mod.login_required
    def api_delete_job(job_id):
        if store.delete(job_id):
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @app.post("/api/jobs/<job_id>/toggle")
    @auth_mod.login_required
    def api_toggle_job(job_id):
        job = store.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404
        updated = store.update(job_id, enabled=not job.get("enabled", True))
        return jsonify(updated)

    @app.get("/api/jobs/<job_id>/log")
    @auth_mod.login_required
    def api_job_log(job_id):
        job = store.get(job_id)
        if not job or not job.get("last_log"):
            return jsonify({"error": "no log"}), 404
        log_path = Path(job["last_log"]).resolve()
        if not _is_within(log_path, logs_dir):
            return jsonify({"error": "invalid log path"}), 400
        try:
            text = log_path.read_text(encoding="utf-8")
        except OSError:
            text = "(log file missing)"
        return jsonify({"log": text})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if auth_mod.check_password(request.form.get("password", "")):
                session["authed"] = True
                nxt = request.args.get("next") or ""
                if not nxt or urlparse(nxt).netloc:   # reject absolute/protocol-relative URLs
                    nxt = url_for("index")
                return redirect(nxt)
            return render_template("login.html", error="Invalid password"), 401
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

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
