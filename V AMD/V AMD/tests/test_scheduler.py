"""
AntiGravity Core v1.0 — Scheduler Unit Tests
Covers all operational constraints and decision logic.
"""

import sys
import os
import time
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from engine.carbon_analyzer import (
    CarbonReading, CarbonForecast, classify_intensity, analyze_carbon_delta,
)
from engine.telemetry import AMDTelemetry, clamp_clock, clamp_tdp, create_telemetry
from engine.job_queue import Job, JobQueue
from engine.scheduler import Scheduler


# ═══════════════════════════════════════════════════════════
# Carbon Analyzer Tests
# ═══════════════════════════════════════════════════════════

class TestCarbonAnalyzer:

    def test_classify_high(self):
        assert classify_intensity(450) == "HIGH"
        assert classify_intensity(401) == "HIGH"

    def test_classify_low(self):
        assert classify_intensity(50) == "LOW"
        assert classify_intensity(99) == "LOW"

    def test_classify_moderate(self):
        assert classify_intensity(100) == "MODERATE"
        assert classify_intensity(250) == "MODERATE"
        assert classify_intensity(400) == "MODERATE"

    def test_analyze_delta_with_forecast(self):
        forecast = CarbonForecast(readings=[
            CarbonReading(timestamp="2026-01-01T00:00:00Z", intensity_gco2=300),
            CarbonReading(timestamp="2026-01-01T01:00:00Z", intensity_gco2=100),
            CarbonReading(timestamp="2026-01-01T02:00:00Z", intensity_gco2=200),
        ])
        result = analyze_carbon_delta(350, forecast)
        assert result["classification"] == "MODERATE"
        assert result["forecast_min"] == 100
        assert result["delta"] == 250

    def test_analyze_delta_no_forecast(self):
        forecast = CarbonForecast(readings=[])
        result = analyze_carbon_delta(200, forecast)
        assert result["forecast_min"] == 200
        assert result["delta"] == 0


# ═══════════════════════════════════════════════════════════
# Telemetry Tests
# ═══════════════════════════════════════════════════════════

class TestTelemetry:

    def test_failsafe_defaults(self):
        t = create_telemetry()
        assert t.current_watts == config.FAILSAFE_TDP_WATTS
        assert t.clock_mhz == config.FAILSAFE_FREQ_GHZ * 1000
        assert t.is_failsafe is True

    def test_clamp_clock_ceiling(self):
        assert clamp_clock(2500) == config.MAX_INSTINCT_CLOCK_MHZ
        assert clamp_clock(2100) == 2100
        assert clamp_clock(1800) == 1800

    def test_clamp_tdp_ceiling(self):
        assert clamp_tdp(500) == config.MAX_EPYC_TDP_WATTS
        assert clamp_tdp(400) == 400
        assert clamp_tdp(200) == 200

    def test_clamp_negative(self):
        assert clamp_clock(-100) == 0
        assert clamp_tdp(-50) == 0

    def test_vram_free(self):
        t = AMDTelemetry(vram_used_gb=64, vram_total_gb=192)
        assert t.vram_free_gb == 128


# ═══════════════════════════════════════════════════════════
# Job Queue Tests
# ═══════════════════════════════════════════════════════════

class TestJobQueue:

    def test_add_and_get(self):
        q = JobQueue()
        j = Job(task_id="T1", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z")
        err = q.add(j)
        assert err is None
        assert q.size == 1
        assert q.get("T1") is not None

    def test_vram_overflow_rejected(self):
        q = JobQueue()
        j = Job(task_id="BIG", priority=1, vram_req_gb=256, deadline="2026-12-31T00:00:00Z")
        err = q.add(j)
        assert err is not None
        assert "exceeds" in err
        assert q.size == 0

    def test_priority_ordering(self):
        q = JobQueue()
        q.add(Job(task_id="LOW", priority=5, vram_req_gb=8, deadline="2026-12-31T00:00:00Z"))
        q.add(Job(task_id="HIGH", priority=1, vram_req_gb=8, deadline="2026-12-31T00:00:00Z"))
        assert q.jobs[0].task_id == "HIGH"

    def test_next_job_vram_filter(self):
        q = JobQueue()
        q.add(Job(task_id="BIG", priority=1, vram_req_gb=100, deadline="2026-12-31T00:00:00Z"))
        q.add(Job(task_id="SMALL", priority=2, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        # Only 50GB available → BIG skipped, SMALL returned
        result = q.next_job(50)
        assert result.task_id == "SMALL"


# ═══════════════════════════════════════════════════════════
# Scheduler Decision Tests
# ═══════════════════════════════════════════════════════════

class TestScheduler:

    def _make_scheduler(self, intensity=200, watts=200, tdp=400, vram_used=0):
        s = Scheduler()
        s.set_carbon(intensity, forecast_readings=[
            {"timestamp": "2026-01-01T00:00:00Z", "intensity": intensity * 0.8},
            {"timestamp": "2026-01-01T01:00:00Z", "intensity": intensity * 0.5},
        ])
        s.set_telemetry(
            current_watts=watts, core_temp_c=70,
            tdp_cap_watts=tdp, clock_mhz=1900,
            vram_used_gb=vram_used, vram_total_gb=192,
        )
        return s

    def test_high_carbon_caps_tdp(self):
        """High carbon → TDP capped at 50 % (Efficiency Mode)."""
        s = self._make_scheduler(intensity=450, tdp=400)
        s.job_queue.add(Job(task_id="T1", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        result = s.decide()
        assert result["decision"]["action"] == "SCALE_DOWN"
        # TDP should be 50 % of 400 = 200W
        assert result["decision"]["amd_tuning"]["target_tdp_watts"] == 200

    def test_low_carbon_pbo(self):
        """Low carbon → Performance Mode (PBO)."""
        s = self._make_scheduler(intensity=50, tdp=400)
        s.job_queue.add(Job(task_id="T2", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        result = s.decide()
        assert result["decision"]["action"] == "EXECUTE"
        assert result["decision"]["amd_tuning"]["p_state"] == 0
        assert result["decision"]["amd_tuning"]["target_tdp_watts"] == 400

    def test_vram_overflow_defers(self):
        """Job VRAM > available → DEFER with error flag."""
        s = self._make_scheduler(intensity=200, vram_used=180)
        s.job_queue.add(Job(task_id="HUGE", priority=1, vram_req_gb=64, deadline="2026-12-31T00:00:00Z"))
        result = s.decide(task_id="HUGE")  # target explicitly to trigger VRAM check
        assert result["decision"]["action"] == "DEFER"
        assert "VRAM_OVERFLOW" in result["error_flags"]

    def test_missing_telemetry_failsafe(self):
        """Missing telemetry → should use Zen 4 fail-safe defaults."""
        s = Scheduler()  # default telemetry is failsafe
        s.set_carbon(200)
        s.job_queue.add(Job(task_id="T3", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        assert s.telemetry.is_failsafe is True
        result = s.decide()
        assert result["decision"]["task_id"] == "T3"

    def test_no_eligible_task(self):
        """Empty queue → DEFER with NO_ELIGIBLE_TASK."""
        s = self._make_scheduler(intensity=200)
        result = s.decide()
        assert result["decision"]["action"] == "DEFER"
        assert result["error_flags"] == "NO_ELIGIBLE_TASK"

    def test_output_schema(self):
        """Verify strict JSON output schema."""
        s = self._make_scheduler(intensity=200)
        s.job_queue.add(Job(task_id="SCHEMA", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        result = s.decide()

        # Top-level keys
        assert "timestamp" in result
        assert "decision" in result
        assert "metrics" in result
        assert "error_flags" in result

        # Decision keys
        d = result["decision"]
        assert "task_id" in d
        assert "action" in d
        assert d["action"] in ("EXECUTE", "DEFER", "SCALE_DOWN")
        assert "amd_tuning" in d
        assert "target_tdp_watts" in d["amd_tuning"]
        assert "core_affinity" in d["amd_tuning"]
        assert "p_state" in d["amd_tuning"]

        # Metrics keys
        m = result["metrics"]
        assert "carbon_saved_est_grams" in m
        assert "confidence_score" in m
        assert 0.0 <= m["confidence_score"] <= 1.0

    def test_physical_boundary_tdp(self):
        """TDP should never exceed 400W even if configured higher."""
        s = self._make_scheduler(intensity=50, tdp=500)  # 500 gets clamped
        s.job_queue.add(Job(task_id="TB", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        result = s.decide()
        assert result["decision"]["amd_tuning"]["target_tdp_watts"] <= config.MAX_EPYC_TDP_WATTS

    def test_history_appended(self):
        """Each decision should be recorded in history."""
        s = self._make_scheduler(intensity=200)
        s.job_queue.add(Job(task_id="H1", priority=1, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        s.decide()
        assert len(s.history) == 1
        s.job_queue.add(Job(task_id="H2", priority=2, vram_req_gb=16, deadline="2026-12-31T00:00:00Z"))
        s.decide()
        assert len(s.history) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
