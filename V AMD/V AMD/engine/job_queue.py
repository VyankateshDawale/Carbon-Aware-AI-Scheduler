"""
AntiGravity Core v1.0 — Job Queue Manager
Priority-sorted job queue with VRAM-fit validation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

import config


@dataclass
class Job:
    """A single compute job in the queue."""
    task_id: str
    priority: int            # 1 (highest) – 10 (lowest)
    vram_req_gb: float       # required VRAM in GB
    deadline: str            # ISO8601 deadline
    status: str = "QUEUED"   # QUEUED | RUNNING | COMPLETED | DEFERRED | FAILED

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "priority": self.priority,
            "vram_req_gb": self.vram_req_gb,
            "deadline": self.deadline,
            "status": self.status,
        }


class JobQueue:
    """Thread-safe priority job queue with VRAM validation."""

    def __init__(self) -> None:
        self._jobs: List[Job] = []

    @property
    def jobs(self) -> List[Job]:
        return sorted(self._jobs, key=lambda j: j.priority)

    @property
    def queued_jobs(self) -> List[Job]:
        return [j for j in self.jobs if j.status == "QUEUED"]

    @property
    def size(self) -> int:
        return len(self._jobs)

    def add(self, job: Job) -> str | None:
        """Add a job. Returns error string if VRAM exceeds MI300X capacity."""
        if job.vram_req_gb > config.MI300X_VRAM_GB:
            return (
                f"VRAM requirement {job.vram_req_gb}GB exceeds "
                f"MI300X capacity {config.MI300X_VRAM_GB}GB"
            )
        self._jobs.append(job)
        return None

    def remove(self, task_id: str) -> bool:
        """Remove a job by task_id. Returns True if found."""
        for i, j in enumerate(self._jobs):
            if j.task_id == task_id:
                self._jobs.pop(i)
                return True
        return False

    def get(self, task_id: str) -> Optional[Job]:
        """Get a job by task_id."""
        for j in self._jobs:
            if j.task_id == task_id:
                return j
        return None

    def update_status(self, task_id: str, status: str) -> bool:
        """Update the status of a job. Returns True if found."""
        job = self.get(task_id)
        if job:
            job.status = status
            return True
        return False

    def next_job(self, available_vram_gb: float) -> Optional[Job]:
        """Get highest-priority queued job that fits available VRAM."""
        for job in self.queued_jobs:
            if job.vram_req_gb <= available_vram_gb:
                return job
        return None

    def to_list(self) -> List[dict]:
        return [j.to_dict() for j in self.jobs]

    def clear(self) -> None:
        self._jobs.clear()

    def is_deadline_urgent(self, job: Job) -> bool:
        """Check if a job's deadline is within 30 minutes."""
        try:
            deadline = datetime.fromisoformat(job.deadline)
            now = datetime.now(deadline.tzinfo)
            remaining = (deadline - now).total_seconds()
            return remaining < 1800  # 30 minutes
        except (ValueError, TypeError):
            return False
