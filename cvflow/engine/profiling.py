"""Run reports: what happened, how long, served from cache or not (docs/02 §9)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class NodeStatus(enum.Enum):
    OK = "ok"                    # executed successfully this run
    CACHED = "cached"            # outputs served from the fingerprint cache
    ERROR = "error"              # process() raised
    CONFIG_ERROR = "config"      # invalid before running (missing input, bad params)
    BLOCKED = "blocked"          # an upstream node failed; not attempted
    SKIPPED = "skipped"          # side-effect node not armed
    CANCELLED = "cancelled"      # run superseded/aborted before this node


@dataclass
class NodeError:
    node_id: str
    message: str
    exc_type: str = ""
    traceback: str = ""


@dataclass
class NodeMetrics:
    status: NodeStatus
    ms: float = 0.0
    ema_ms: float | None = None
    cache_hit: bool = False
    out_bytes: int = 0
    error: str = ""


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    bytes_used: int = 0
    budget_bytes: int = 0
    entries: int = 0
    evictions: int = 0


@dataclass
class RunReport:
    generation: int
    wall_ms: float = 0.0
    mode: str = "interactive"
    nodes: dict[str, NodeMetrics] = field(default_factory=dict)
    errors: list[NodeError] = field(default_factory=list)
    cache: CacheStats = field(default_factory=CacheStats)

    @property
    def ok(self) -> bool:
        return not self.errors

    def executed(self) -> list[str]:
        return [nid for nid, m in self.nodes.items() if m.status is NodeStatus.OK]

    def cached(self) -> list[str]:
        return [nid for nid, m in self.nodes.items() if m.status is NodeStatus.CACHED]

    def to_text(self) -> str:
        """Plain-text table for CLI output and logs."""
        lines = [f"run #{self.generation}  {self.wall_ms:.1f} ms  "
                 f"cache {self.cache.hits}/{self.cache.hits + self.cache.misses} hits"]
        width = max((len(nid) for nid in self.nodes), default=4)
        for nid, m in self.nodes.items():
            mark = {"ok": "+", "cached": "=", "skipped": "·"}.get(m.status.value, "!")
            err = f"  {m.error}" if m.error else ""
            lines.append(f"  {mark} {nid:<{width}}  {m.status.value:<8} {m.ms:7.1f} ms{err}")
        return "\n".join(lines)
