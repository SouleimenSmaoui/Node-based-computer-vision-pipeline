"""Param-to-pixel latency probe (docs/08 Phase-1 exit criterion).

docs/08 gates Phase 1 on *measured* param-to-pixel p95 < 100 ms at 1080p. Until
now that number was only ever estimated from engine timings, which undercount:
the engine's ``wall_ms`` covers the run, not the debounce before it, the queued
signal delivery after it, or any backlog on the GUI thread.

So both ends of the measurement live on the GUI thread — :meth:`mark_edit` when
a parameter edit is applied, :meth:`measure` when a viewer actually sets a
pixmap. The sample is then everything the user waits through, which is the only
version of the number worth gating on.

No Qt here on purpose: this is plain arithmetic and is tested as such.
"""

from __future__ import annotations

import math
import time
from collections import deque


class LatencyProbe:
    """Edit → displayed-pixel latencies, in milliseconds.

    Single-threaded by design: call every method from the GUI thread.
    """

    def __init__(self, capacity: int = 200) -> None:
        self._samples: deque[float] = deque(maxlen=capacity)
        self._pending: float | None = None
        self._clock = time.perf_counter

    # ---- recording ---------------------------------------------------------
    def mark_edit(self) -> None:
        """A parameter edit just happened.

        The newest edit wins: a run in flight cannot reflect an edit made after
        it started, and a burst of slider ticks deliberately collapses into one
        launch (docs/05 §2.3). Overwriting therefore measures the edit the next
        frame will actually show, not the oldest one still queued.
        """
        self._pending = self._clock()

    def measure(self) -> float | None:
        """Record the pending edit's latency; ``None`` if no edit is pending.

        No edit pending is the normal case for a viewer update the user did not
        trigger by editing (switching viewers, opening a workflow).
        """
        if self._pending is None:
            return None
        ms = (self._clock() - self._pending) * 1000.0
        self._pending = None
        self._samples.append(ms)
        return ms

    def discard_pending(self) -> None:
        """Drop an edit that produced no visible update.

        Editing a node no viewer depends on still completes a run, but nothing
        repaints. Without dropping it, that timestamp would survive to be
        charged against some later, unrelated frame.
        """
        self._pending = None

    # ---- reading -----------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self._samples)

    def percentile(self, pct: float) -> float | None:
        """Nearest-rank percentile — no interpolation, so every value returned
        is a sample that actually occurred. Honest at small n, which is what
        this has: a tuning session produces tens, not millions."""
        if not self._samples:
            return None
        ordered = sorted(self._samples)
        rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
        return ordered[min(rank, len(ordered)) - 1]

    def summary(self) -> str:
        """One-line status-bar text; empty until there is something to report."""
        p95 = self.percentile(95)
        if p95 is None:
            return ""
        return f"param→pixel p95 {p95:.0f} ms (n={len(self._samples)})"

    def reset(self) -> None:
        self._samples.clear()
        self._pending = None
