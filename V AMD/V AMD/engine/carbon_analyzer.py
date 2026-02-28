"""
AntiGravity Core v1.0 — Carbon Analyzer
Analyzes grid carbon intensity against forecast to determine operating mode.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

import config


@dataclass
class CarbonReading:
    """A single grid carbon intensity reading."""
    timestamp: str          # ISO8601
    intensity_gco2: float   # gCO2/kWh


@dataclass
class CarbonForecast:
    """6-hour carbon intensity forecast."""
    readings: List[CarbonReading] = field(default_factory=list)

    @property
    def minimum(self) -> Optional[CarbonReading]:
        if not self.readings:
            return None
        return min(self.readings, key=lambda r: r.intensity_gco2)

    @property
    def maximum(self) -> Optional[CarbonReading]:
        if not self.readings:
            return None
        return max(self.readings, key=lambda r: r.intensity_gco2)

    @property
    def average(self) -> float:
        if not self.readings:
            return 0.0
        return sum(r.intensity_gco2 for r in self.readings) / len(self.readings)


def classify_intensity(intensity_gco2: float) -> str:
    """Classify carbon intensity into an operating band.

    Returns:
        'HIGH'      — intensity > 400 gCO2/kWh  →  Efficiency Mode
        'LOW'       — intensity < 100 gCO2/kWh  →  Performance Mode
        'MODERATE'  — everything in between      →  Balanced Mode
    """
    if intensity_gco2 > config.CARBON_HIGH_THRESHOLD:
        return "HIGH"
    elif intensity_gco2 < config.CARBON_LOW_THRESHOLD:
        return "LOW"
    else:
        return "MODERATE"


def analyze_carbon_delta(
    current_intensity: float,
    forecast: CarbonForecast,
) -> dict:
    """Compare current intensity to the forecast minimum and return analysis.

    Returns dict with:
        classification  — 'HIGH' | 'MODERATE' | 'LOW'
        current         — current gCO2/kWh
        forecast_min    — lowest forecasted gCO2/kWh (or current if no forecast)
        delta           — current − forecast_min
        should_defer    — True if deferring would save significant carbon
    """
    classification = classify_intensity(current_intensity)
    forecast_min_reading = forecast.minimum
    forecast_min = forecast_min_reading.intensity_gco2 if forecast_min_reading else current_intensity

    delta = current_intensity - forecast_min

    # If the forecast minimum is significantly lower (>20 % reduction), deferring helps
    should_defer = delta > 0 and (delta / max(current_intensity, 1.0)) > 0.20

    return {
        "classification": classification,
        "current": current_intensity,
        "forecast_min": forecast_min,
        "forecast_min_time": forecast_min_reading.timestamp if forecast_min_reading else None,
        "delta": round(delta, 2),
        "should_defer": should_defer,
        "forecast_avg": round(forecast.average, 2),
    }
