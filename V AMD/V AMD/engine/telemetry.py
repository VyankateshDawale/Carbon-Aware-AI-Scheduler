"""
AntiGravity Core v1.0 — AMD Telemetry
Dataclasses and clamping for AMD EPYC / Instinct hardware telemetry.
"""

from __future__ import annotations
from dataclasses import dataclass

import config


@dataclass
class AMDTelemetry:
    """Real-time AMD hardware telemetry snapshot."""
    current_watts: float = config.FAILSAFE_TDP_WATTS
    core_temp_c: float = 65.0
    tdp_cap_watts: float = config.FAILSAFE_TDP_WATTS
    clock_mhz: float = config.FAILSAFE_FREQ_GHZ * 1000
    vram_used_gb: float = 0.0
    vram_total_gb: float = config.MI300X_VRAM_GB

    @property
    def vram_free_gb(self) -> float:
        return max(0.0, self.vram_total_gb - self.vram_used_gb)

    @property
    def tdp_utilization_pct(self) -> float:
        if self.tdp_cap_watts <= 0:
            return 0.0
        return round((self.current_watts / self.tdp_cap_watts) * 100, 1)

    @property
    def is_failsafe(self) -> bool:
        """True if running on Zen4 fail-safe defaults."""
        return (
            self.current_watts == config.FAILSAFE_TDP_WATTS
            and self.clock_mhz == config.FAILSAFE_FREQ_GHZ * 1000
        )

    def to_dict(self) -> dict:
        return {
            "current_watts": self.current_watts,
            "core_temp_c": self.core_temp_c,
            "tdp_cap_watts": self.tdp_cap_watts,
            "clock_mhz": self.clock_mhz,
            "vram_used_gb": round(self.vram_used_gb, 1),
            "vram_total_gb": self.vram_total_gb,
            "vram_free_gb": round(self.vram_free_gb, 1),
            "tdp_utilization_pct": self.tdp_utilization_pct,
            "is_failsafe": self.is_failsafe,
        }


def clamp_clock(clock_mhz: float) -> float:
    """Clamp clock speed to AMD Instinct physical ceiling."""
    return min(max(clock_mhz, 0), config.MAX_INSTINCT_CLOCK_MHZ)


def clamp_tdp(tdp_watts: float) -> float:
    """Clamp TDP to AMD EPYC physical ceiling."""
    return min(max(tdp_watts, 0), config.MAX_EPYC_TDP_WATTS)


def create_telemetry(
    current_watts: float | None = None,
    core_temp_c: float | None = None,
    tdp_cap_watts: float | None = None,
    clock_mhz: float | None = None,
    vram_used_gb: float | None = None,
    vram_total_gb: float | None = None,
) -> AMDTelemetry:
    """Create an AMDTelemetry instance with fail-safe defaults for missing values."""
    return AMDTelemetry(
        current_watts=clamp_tdp(current_watts) if current_watts is not None else config.FAILSAFE_TDP_WATTS,
        core_temp_c=core_temp_c if core_temp_c is not None else 65.0,
        tdp_cap_watts=clamp_tdp(tdp_cap_watts) if tdp_cap_watts is not None else config.FAILSAFE_TDP_WATTS,
        clock_mhz=clamp_clock(clock_mhz) if clock_mhz is not None else config.FAILSAFE_FREQ_GHZ * 1000,
        vram_used_gb=vram_used_gb if vram_used_gb is not None else 0.0,
        vram_total_gb=vram_total_gb if vram_total_gb is not None else config.MI300X_VRAM_GB,
    )
