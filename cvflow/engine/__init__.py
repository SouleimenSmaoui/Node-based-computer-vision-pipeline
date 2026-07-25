"""Execution engine: scheduling, fingerprint caching, reporting (docs/02).

Pure Python over the core model — no Qt, no GUI concepts. Clients (CLI today,
GUI in Phase 1) drive it through ExecutionService and subscribe to its hooks.
"""

from cvflow.engine.executor import EngineSettings, ExecutionService
from cvflow.engine.profiling import NodeStatus, RunReport

__all__ = ["EngineSettings", "ExecutionService", "NodeStatus", "RunReport"]
