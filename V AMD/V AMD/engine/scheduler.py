"""
AntiGravity Core v1.0 — Scheduler Decision Engine
Deterministic workload scheduler with carbon-aware AMD hardware tuning.
"""

from __future__ import annotations

import time
import math
from datetime import datetime, timezone
from typing import Optional, List

import config
from engine.carbon_analyzer import CarbonForecast, CarbonReading, analyze_carbon_delta, classify_intensity
from engine.telemetry import AMDTelemetry, clamp_tdp, clamp_clock, create_telemetry
from engine.job_queue import Job, JobQueue


class SchedulerDecision:
    """Encapsulates a single scheduler decision in strict JSON form."""

    def __init__(
        self,
        task_id: str,
        action: str,
        target_tdp_watts: int,
        core_affinity: List[int],
        p_state: int,
        carbon_saved_est_grams: float,
        confidence_score: float,
        error_flags: Optional[str] = None,
    ):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.task_id = task_id
        self.action = action                    # EXECUTE | DEFER | SCALE_DOWN
        self.target_tdp_watts = target_tdp_watts
        self.core_affinity = core_affinity
        self.p_state = p_state
        self.carbon_saved_est_grams = round(carbon_saved_est_grams, 2)
        self.confidence_score = round(min(max(confidence_score, 0.0), 1.0), 2)
        self.error_flags = error_flags

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "decision": {
                "task_id": self.task_id,
                "action": self.action,
                "amd_tuning": {
                    "target_tdp_watts": self.target_tdp_watts,
                    "core_affinity": self.core_affinity,
                    "p_state": self.p_state,
                },
            },
            "metrics": {
                "carbon_saved_est_grams": self.carbon_saved_est_grams,
                "confidence_score": self.confidence_score,
            },
            "error_flags": self.error_flags,
        }


class Scheduler:
    """Main decision engine for AntiGravity Core."""

    def __init__(self) -> None:
        self.job_queue = JobQueue()
        self.telemetry = create_telemetry()
        self.current_intensity: float = 200.0
        self.forecast = CarbonForecast()
        self.history: List[dict] = []
        self._default_cores = list(range(0, 16))

    # ── public API ──────────────────────────────────────────

    def set_telemetry(self, **kwargs) -> None:
        self.telemetry = create_telemetry(**kwargs)

    def set_carbon(self, current: float, forecast_readings: List[dict] | None = None) -> None:
        self.current_intensity = current
        if forecast_readings:
            self.forecast = CarbonForecast(
                readings=[
                    CarbonReading(timestamp=r["timestamp"], intensity_gco2=r["intensity"])
                    for r in forecast_readings
                ]
            )

    def decide(self, task_id: str | None = None) -> dict:
        """Run one decision cycle. Respects 250ms anti-hang budget."""
        t0 = time.perf_counter()

        # If no specific task_id, pick next from queue
        job: Optional[Job] = None
        if task_id:
            job = self.job_queue.get(task_id)
        else:
            job = self.job_queue.next_job(self.telemetry.vram_free_gb)

        if not job:
            decision = SchedulerDecision(
                task_id="NONE",
                action="DEFER",
                target_tdp_watts=int(clamp_tdp(config.FAILSAFE_TDP_WATTS)),
                core_affinity=self._default_cores,
                p_state=config.BALANCED_MODE["p_state"],
                carbon_saved_est_grams=0.0,
                confidence_score=0.5,
                error_flags="NO_ELIGIBLE_TASK",
            )
            result = decision.to_dict()
            self.history.append(result)
            return result

        # ── Step 1: Carbon analysis ─────────────────────────
        carbon = analyze_carbon_delta(self.current_intensity, self.forecast)
        classification = carbon["classification"]

        # ── Anti-hang check ─────────────────────────────────
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > config.DECISION_TIMEOUT_MS:
            return self._timeout_defer(job.task_id)

        # ── Step 2: VRAM validation ─────────────────────────
        if job.vram_req_gb > self.telemetry.vram_free_gb:
            decision = SchedulerDecision(
                task_id=job.task_id,
                action="DEFER",
                target_tdp_watts=int(clamp_tdp(self.telemetry.tdp_cap_watts)),
                core_affinity=self._default_cores,
                p_state=config.BALANCED_MODE["p_state"],
                carbon_saved_est_grams=0.0,
                confidence_score=0.9,
                error_flags=f"VRAM_OVERFLOW: need {job.vram_req_gb}GB, have {self.telemetry.vram_free_gb}GB",
            )
            self.job_queue.update_status(job.task_id, "DEFERRED")
            result = decision.to_dict()
            self.history.append(result)
            return result

        # ── Step 3: Hardware mapping ────────────────────────
        if classification == "HIGH":
            # Efficiency Mode — cap TDP at 50 %
            mode = config.EFFICIENCY_MODE
            target_tdp = int(clamp_tdp(self.telemetry.tdp_cap_watts * mode["tdp_cap_pct"]))
            action = "SCALE_DOWN"
            p_state = mode["p_state"]
        elif classification == "LOW":
            # Performance Mode — PBO
            mode = config.PERFORMANCE_MODE
            target_tdp = int(clamp_tdp(self.telemetry.tdp_cap_watts * mode["tdp_cap_pct"]))
            action = "EXECUTE"
            p_state = mode["p_state"]
        else:
            # Balanced / Moderate
            mode = config.BALANCED_MODE

            # Check if deferring is smarter (forecast shows big improvement)
            if carbon["should_defer"] and not self.job_queue.is_deadline_urgent(job):
                target_tdp = int(clamp_tdp(self.telemetry.tdp_cap_watts * mode["tdp_cap_pct"]))
                action = "DEFER"
                p_state = mode["p_state"]
            else:
                target_tdp = int(clamp_tdp(self.telemetry.tdp_cap_watts * mode["tdp_cap_pct"]))
                action = "EXECUTE"
                p_state = mode["p_state"]

        # ── Step 4: Efficiency ratio & carbon saving ────────
        efficiency_ratio = self._calc_efficiency_ratio(self.current_intensity)
        carbon_saved = self._estimate_carbon_saved(
            action, self.telemetry.tdp_cap_watts, target_tdp, self.current_intensity
        )

        # ── Anti-hang final check ───────────────────────────
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > config.DECISION_TIMEOUT_MS:
            return self._timeout_defer(job.task_id)

        # ── Confidence score ────────────────────────────────
        confidence = self._compute_confidence(carbon, job)

        # ── Build decision ──────────────────────────────────
        decision = SchedulerDecision(
            task_id=job.task_id,
            action=action,
            target_tdp_watts=target_tdp,
            core_affinity=self._default_cores,
            p_state=p_state,
            carbon_saved_est_grams=carbon_saved,
            confidence_score=confidence,
            error_flags=None,
        )

        # Update job status
        if action == "EXECUTE":
            self.job_queue.update_status(job.task_id, "RUNNING")
        elif action == "DEFER":
            self.job_queue.update_status(job.task_id, "DEFERRED")
        elif action == "SCALE_DOWN":
            self.job_queue.update_status(job.task_id, "RUNNING")

        result = decision.to_dict()
        self.history.append(result)
        return result

    def get_status(self) -> dict:
        """Return current engine state summary."""
        carbon = analyze_carbon_delta(self.current_intensity, self.forecast)
        return {
            "engine": "AntiGravity Core v1.0",
            "carbon": {
                "current_intensity": self.current_intensity,
                "classification": carbon["classification"],
                "forecast_min": carbon["forecast_min"],
                "forecast_avg": carbon["forecast_avg"],
                "delta": carbon["delta"],
            },
            "telemetry": self.telemetry.to_dict(),
            "queue": {
                "total_jobs": self.job_queue.size,
                "queued": len(self.job_queue.queued_jobs),
                "jobs": self.job_queue.to_list(),
            },
            "last_decision": self.history[-1] if self.history else None,
            "decisions_made": len(self.history),
        }

    # ── private helpers ─────────────────────────────────────

    def _calc_efficiency_ratio(self, current_gco2: float) -> float:
        """R = Expected TFLOPS / Real-time gCO2."""
        if current_gco2 <= 0:
            return float("inf")
        return round(config.REFERENCE_TFLOPS_FP16 / current_gco2, 4)

    def _estimate_carbon_saved(
        self, action: str, original_tdp: float, target_tdp: float, intensity: float
    ) -> float:
        """Estimate grams of CO2 saved by scaling down, over a 1-hour window."""
        if action == "EXECUTE":
            return 0.0
        watt_reduction = max(0, original_tdp - target_tdp)
        kwh_saved = watt_reduction / 1000.0   # 1 hour
        return round(kwh_saved * intensity, 2)

    def _compute_confidence(self, carbon_analysis: dict, job: Job) -> float:
        """Heuristic confidence score based on data quality."""
        score = 0.7  # base

        # Boost if we have a forecast
        if carbon_analysis["forecast_min"] != carbon_analysis["current"]:
            score += 0.1

        # Boost if telemetry is real (not failsafe)
        if not self.telemetry.is_failsafe:
            score += 0.1

        # Slight penalty if VRAM is tight
        if job.vram_req_gb > self.telemetry.vram_free_gb * 0.8:
            score -= 0.1

        return min(max(score, 0.0), 1.0)

    def _timeout_defer(self, task_id: str) -> dict:
        """Anti-hang: decision took too long, default to DEFER_TASK."""
        decision = SchedulerDecision(
            task_id=task_id,
            action="DEFER",
            target_tdp_watts=int(clamp_tdp(config.FAILSAFE_TDP_WATTS)),
            core_affinity=self._default_cores,
            p_state=config.BALANCED_MODE["p_state"],
            carbon_saved_est_grams=0.0,
            confidence_score=0.3,
            error_flags="ANTI_HANG_TIMEOUT_250MS",
        )
        result = decision.to_dict()
        self.history.append(result)
        return result
