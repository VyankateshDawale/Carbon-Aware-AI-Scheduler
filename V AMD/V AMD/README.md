# AntiGravity Core v1.0

A carbon-aware, deterministic workload scheduler designed specifically for AMD EPYC™ and Instinct™ hardware.

## Overview

AntiGravity Core connects real-time grid carbon intensity forecasts with AMD hardware telemetry to intelligently schedule computational workloads. It enforces strict physical boundaries and deterministic logic to ensure zero-hallucination execution.

### Key Features
- **Carbon-Aware Scheduling**: Dynamically shifts between Efficiency Mode (50% TDP cap) and Performance Mode (PBO) based on local grid carbon intensity (gCO2/kWh).
- **AMD Hardware Telemetry**: Monitors real-time Watts, Core Temperature, and TDP Caps, with automatic clamping to prevent hardware damage.
- **Fail-Safe Determinism**: Uses guaranteed fallback constants (e.g., TDP=120W, Freq=2.0GHz for Zen 4) if live telemetry is unavailable.
- **VRAM Validation**: Enforces strict memory checks against the AMD Instinct MI300X (192GB) capacity before dequeuing jobs.
- **Anti-Hang Protocol**: Enforces a strict 250ms compute boundary on the decision loop, aggressively deferring tasks to prevent system bottlenecks.
- **Dashboard Interface**: A professional, enterprise-grade dark/light theme dashboard for monitoring carbon deltas, hardware utilization, and the active job queue.

## Project Architecture

``` text
V AMD/
├── config.py                  # Core deterministic constants and boundaries
├── server.py                  # Flask REST API and static file handling
├── run.py                     # Entry point
├── engine/
│   ├── carbon_analyzer.py     # Grid intensity logic and classification
│   ├── job_queue.py           # Priority sorting and VRAM validation
│   ├── scheduler.py           # The deterministic decision loop
│   └── telemetry.py           # Hardware boundary enforcement and mock data
├── static/
│   ├── index.html             # Dashboard markup
│   ├── style.css              # Enterprise UI (Dark/Light mode)
│   └── app.js                 # API polling and chart rendering
└── tests/
    └── test_scheduler.py      # Comprehensive rule validation suite
```

## Setup & Installation

**Prerequisites:** Python 3.9+

1. Install dependencies:
   ```bash
   pip install flask flask-cors pytest
   ```

2. Run the application:
   ```bash
   python run.py
   ```

3. Open the dashboard in your browser:
   ```text
   http://localhost:5000
   ```

## API Endpoints

The core engine exposes a REST API for integration:

- `GET /api/status` - Aggregated view of carbon, telemetry, and queue.
- `GET /api/carbon` - Current intensity and 6-hour forecast delta.
- `GET /api/telemetry` - Live AMD hardware metrics.
- `GET /api/jobs` - View the prioritized job queue.
- `POST /api/jobs` - Add a new task (requires `task_id`, `priority`, `vram_req_gb`, `deadline`).
- `POST /api/decide` - Manually trigger the scheduler decision loop.
- `GET /api/history` - Retrieve the JSON logs of past decisions.

## Testing

The project includes a comprehensive test suite (22 tests) guaranteeing that the scheduler adheres to the strict operational constraints.

```bash
pytest tests/
```
