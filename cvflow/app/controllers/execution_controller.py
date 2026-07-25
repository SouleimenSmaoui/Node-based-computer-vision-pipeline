"""ExecutionController — the debounced, superseding client of ExecutionService
(docs/02 §4, §8; STATUS.md "Next steps" item 2).

The engine's ``run()`` is blocking by design. This controller wraps it so the
interactive loop stays responsive:

* **Debounce** — a param edit schedules a run 30 ms later; a burst of slider
  ticks collapses into one launch.
* **Supersession (latest-wins)** — a new request cancels the in-flight run via a
  ``CancellationToken`` (the engine checks it between nodes) and the worker
  immediately re-runs with current state.
* **Thread hand-off** — ``run()`` executes on a background thread; the engine's
  plain-callback hooks re-emit as Qt signals, delivered to the GUI thread by
  queued connections. The GUI never blocks on the engine.
* **Edit serialization** — structural graph mutations (add/remove/connect) go
  through :meth:`mutate`, which cancels the current run and takes the run-lock
  the worker holds during ``run()``. Param edits skip the lock: the engine takes
  one coherent snapshot of each node's params at dispatch, so an edit landing
  mid-run can at worst waste a superseded run — it can never make a node execute
  with values other than the ones its cache entry is keyed on. (Before that
  snapshot existed the claim here was that param edits were simply "benign";
  they were not — see CODE_REVIEW §1.1.)
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Iterable

from PySide6 import QtCore

from cvflow.core.graph import Graph
from cvflow.engine import EngineSettings, ExecutionService
from cvflow.engine.context import CancellationToken, Resources
from cvflow.engine.profiling import NodeMetrics

DEBOUNCE_MS = 30


class ExecutionController(QtCore.QObject):
    # All emitted from the worker thread; delivered queued to the GUI thread.
    runStarted = QtCore.Signal()
    reportReady = QtCore.Signal(object)           # RunReport
    nodeStatus = QtCore.Signal(str, object)       # (node_id, NodeMetrics)
    outputsReady = QtCore.Signal(str, object)     # (node_id, dict[port, value])

    def __init__(
        self,
        graph: Graph,
        *,
        base_dir: str | None = None,
        settings: EngineSettings | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.graph = graph
        self.service = ExecutionService(graph, settings or EngineSettings(),
                                        Resources(base_dir=base_dir))
        self.service.hooks.on_node_status.append(self._on_node_status)
        self.service.hooks.on_outputs.append(self._on_outputs)

        self._observed: set[str] = set()
        self._armed: set[str] = set()

        self._lock = threading.Lock()          # run-lock (held during service.run)
        self._cond = threading.Condition()
        self._dirty = False
        self._stop = False
        self._token: CancellationToken | None = None

        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._kick)

        self._worker = threading.Thread(target=self._loop, name="cvflow-run", daemon=True)
        self._worker.start()

    # ---- observation / arming ---------------------------------------------
    def set_observed(self, node_ids: Iterable[str]) -> None:
        """Which node outputs the viewers currently watch (demand roots)."""
        new = {n for n in node_ids if n}
        if new != self._observed:
            self._observed = new
            self.schedule()

    def add_observed(self, node_id: str) -> None:
        if node_id and node_id not in self._observed:
            self._observed = self._observed | {node_id}
            self.schedule()

    def arm_and_run(self, sink_ids: Iterable[str]) -> None:
        """Arm side-effect nodes for exactly the next run (Run button)."""
        self._armed = {n for n in sink_ids if n in self.graph.nodes}
        self._launch_now()

    # ---- scheduling --------------------------------------------------------
    def schedule(self) -> None:
        """Request a (debounced) re-run — call after a param change."""
        self._debounce.start()

    def _kick(self) -> None:
        self._launch_now()

    def _launch_now(self) -> None:
        with self._cond:
            self._dirty = True
            if self._token is not None:
                self._token.cancel()   # supersede any in-flight run
            self._cond.notify()

    # ---- structural edits (serialized against the worker) -----------------
    def mutate(self, fn: Callable[[], Any]) -> Any:
        """Run a structural graph edit safely, then reschedule.

        Cancels the in-flight run (so the lock frees quickly) and holds the
        run-lock across ``fn`` so the worker never iterates a half-edited graph.
        """
        with self._cond:
            if self._token is not None:
                self._token.cancel()
        with self._lock:
            result = fn()
        self.schedule()
        return result

    # ---- worker loop -------------------------------------------------------
    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._dirty and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                self._dirty = False
                token = CancellationToken()
                self._token = token
                observed = set(self._observed)
                armed = set(self._armed)
                self._armed = set()

            if not observed and not armed:
                continue

            self.runStarted.emit()
            with self._lock:
                try:
                    report = self.service.run(observed=observed, armed=armed,
                                              token=token, mode="interactive")
                except Exception as exc:  # a controller bug must not kill the thread
                    import logging
                    logging.getLogger("cvflow.app").exception("run failed: %s", exc)
                    continue
            # Skip reporting a run we already know is stale (about to redo).
            with self._cond:
                superseded = self._dirty
            if not superseded:
                self.reportReady.emit(report)

    # ---- engine hooks (worker thread) → Qt signals -------------------------
    def _on_node_status(self, node_id: str, metrics: NodeMetrics) -> None:
        self.nodeStatus.emit(node_id, metrics)

    def _on_outputs(self, node_id: str, outputs: dict[str, Any]) -> None:
        self.outputsReady.emit(node_id, dict(outputs))

    # ---- values ------------------------------------------------------------
    def get_output(self, node_id: str, port: str | None = None) -> Any:
        return self.service.get_output(node_id, port)

    # ---- lifecycle ---------------------------------------------------------
    def shutdown(self) -> None:
        with self._cond:
            self._stop = True
            if self._token is not None:
                self._token.cancel()
            self._cond.notify()
        self._worker.join(timeout=2.0)
        try:
            self.service.close()
        except Exception:
            pass
