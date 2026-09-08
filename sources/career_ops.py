from __future__ import annotations

from orchestrator.models import Job


class CareerOpsSource:
    name = "career_ops"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def fetch(self) -> list[Job]:
        if not self.enabled:
            print("career_ops: disabled", flush=True)
            return []
        raise NotImplementedError("Configure the real Career Ops integration first")

