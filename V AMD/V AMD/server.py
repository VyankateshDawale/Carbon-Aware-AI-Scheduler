"""
AntiGravity Core v1.0 — Flask REST API Server
Bridges the scheduler engine to the web dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from engine.scheduler import Scheduler
from engine.job_queue import Job

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ── Global scheduler instance ──────────────────────────────
scheduler = Scheduler()


def _seed_mock_data() -> None:
    """Pre-populate with realistic demo data."""
    now = datetime.now(timezone.utc)

    # Carbon: current + 6h forecast
    forecast = []
    intensities = [320, 280, 210, 150, 90, 130, 180, 250, 310, 350, 290, 220]
    for i, val in enumerate(intensities):
        forecast.append({
            "timestamp": (now + timedelta(minutes=30 * i)).isoformat(),
            "intensity": val,
        })

    scheduler.set_carbon(current=345.0, forecast_readings=forecast)

    # Telemetry
    scheduler.set_telemetry(
        current_watts=285.0,
        core_temp_c=72.0,
        tdp_cap_watts=400.0,
        clock_mhz=1980.0,
        vram_used_gb=64.0,
        vram_total_gb=192.0,
    )

    # Jobs
    jobs = [
        Job(task_id="LLM-TRAIN-7B", priority=1, vram_req_gb=80.0,
            deadline=(now + timedelta(hours=4)).isoformat(), status="QUEUED"),
        Job(task_id="IMG-INFER-BATCH", priority=2, vram_req_gb=24.0,
            deadline=(now + timedelta(hours=1)).isoformat(), status="QUEUED"),
        Job(task_id="RAG-INDEX-REBUILD", priority=3, vram_req_gb=16.0,
            deadline=(now + timedelta(hours=6)).isoformat(), status="QUEUED"),
        Job(task_id="FINE-TUNE-13B", priority=4, vram_req_gb=120.0,
            deadline=(now + timedelta(hours=8)).isoformat(), status="QUEUED"),
        Job(task_id="EMBEDDINGS-GEN", priority=5, vram_req_gb=8.0,
            deadline=(now + timedelta(hours=2)).isoformat(), status="QUEUED"),
    ]
    for j in jobs:
        scheduler.job_queue.add(j)


_seed_mock_data()


# ── Routes ──────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def api_status():
    return jsonify(scheduler.get_status())


@app.route("/api/telemetry", methods=["GET", "POST"])
def api_telemetry():
    if request.method == "POST":
        data = request.get_json(force=True)
        scheduler.set_telemetry(**data)
        return jsonify({"ok": True})
    return jsonify(scheduler.telemetry.to_dict())


@app.route("/api/carbon", methods=["GET", "POST"])
def api_carbon():
    if request.method == "POST":
        data = request.get_json(force=True)
        scheduler.set_carbon(
            current=data.get("current", 200),
            forecast_readings=data.get("forecast"),
        )
        return jsonify({"ok": True})
    from engine.carbon_analyzer import analyze_carbon_delta
    return jsonify(analyze_carbon_delta(scheduler.current_intensity, scheduler.forecast))


@app.route("/api/jobs", methods=["GET", "POST", "DELETE"])
def api_jobs():
    if request.method == "POST":
        data = request.get_json(force=True)
        job = Job(
            task_id=data["task_id"],
            priority=int(data.get("priority", 5)),
            vram_req_gb=float(data.get("vram_req_gb", 0)),
            deadline=data.get("deadline", datetime.now(timezone.utc).isoformat()),
        )
        err = scheduler.job_queue.add(job)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "job": job.to_dict()})

    if request.method == "DELETE":
        data = request.get_json(force=True)
        removed = scheduler.job_queue.remove(data.get("task_id", ""))
        return jsonify({"ok": removed})

    return jsonify(scheduler.job_queue.to_list())


@app.route("/api/decide", methods=["POST"])
def api_decide():
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id")
    result = scheduler.decide(task_id=task_id)
    return jsonify(result)


@app.route("/api/history")
def api_history():
    return jsonify(scheduler.history[-50:])  # last 50


# ── Entry point ─────────────────────────────────────────────
if __name__ == "__main__":
    import config as cfg
    print(f"\n⚡ AntiGravity Core v1.0 — http://localhost:{cfg.SERVER_PORT}\n")
    app.run(host=cfg.SERVER_HOST, port=cfg.SERVER_PORT, debug=True)
