"""
AntiGravity Core v1.0 — Configuration & Deterministic Constants
All physical boundaries and fail-safe values for AMD EPYC / Instinct hardware.
"""

# ──────────────────────────────────────────────
# AMD Zen 4 Fail-Safe Defaults (used when telemetry is missing)
# ──────────────────────────────────────────────
FAILSAFE_TDP_WATTS = 120
FAILSAFE_FREQ_GHZ = 2.0

# ──────────────────────────────────────────────
# Physical Boundaries (hard ceilings, never exceeded)
# ──────────────────────────────────────────────
MAX_INSTINCT_CLOCK_MHZ = 2100
MAX_EPYC_TDP_WATTS = 400
MI300X_VRAM_GB = 192

# ──────────────────────────────────────────────
# Carbon Intensity Thresholds (gCO2/kWh)
# ──────────────────────────────────────────────
CARBON_HIGH_THRESHOLD = 400   # above → Efficiency Mode
CARBON_LOW_THRESHOLD = 100    # below → Performance Mode (PBO)

# ──────────────────────────────────────────────
# Anti-Hang Protocol
# ──────────────────────────────────────────────
DECISION_TIMEOUT_MS = 250

# ──────────────────────────────────────────────
# Hardware Tuning Presets
# ──────────────────────────────────────────────
EFFICIENCY_MODE = {
    "tdp_cap_pct": 0.50,        # 50 % of rated TDP
    "p_state": 3,               # conservative power state
    "label": "Efficiency Mode",
}

PERFORMANCE_MODE = {
    "tdp_cap_pct": 1.00,        # full TDP
    "p_state": 0,               # top P-state (PBO)
    "label": "Performance Mode (PBO)",
}

BALANCED_MODE = {
    "tdp_cap_pct": 0.75,        # 75 % of rated TDP
    "p_state": 1,               # moderate P-state
    "label": "Balanced Mode",
}

# ──────────────────────────────────────────────
# Reference TFLOPS (AMD Instinct MI300X, FP16)
# ──────────────────────────────────────────────
REFERENCE_TFLOPS_FP16 = 1307.4   # peak spec

# ──────────────────────────────────────────────
# Server
# ──────────────────────────────────────────────
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
