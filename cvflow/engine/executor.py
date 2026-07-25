"""ExecutionService: demand-driven, fingerprint-cached, parallel execution
(docs/02 §2–§6, §8).

Phase 0 simplification (documented in STATUS.md): there is no separate dirty
set — parameters and external state are part of the fingerprint, so any change
is a cache miss by construction. ``run()`` is blocking; the GUI's debounced
async controller arrives in Phase 1 and wraps this service in a thread.
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from cvflow.core.errors import CVFlowError, NodeExecutionError, ParamError
from cvflow.core.graph import Graph, GraphListener, NodeInstance
from cvflow.core.node import Node
from cvflow.engine.cache import OutputCache, collect_input_fps, node_fingerprint
from cvflow.engine.context import (
    CancellationToken,
    ExecutionContext,
    Resources,
)
from cvflow.engine.profiling import (
    NodeError,
    NodeMetrics,
    NodeStatus,
    RunReport,
)

log = logging.getLogger("cvflow.engine")


@dataclass
class EngineSettings:
    workers: int = min(4, os.cpu_count() or 1)  # 0 = execute inline (deterministic)
    cache_budget_bytes: int = 2 * 1024**3
    ema_alpha: float = 0.3


@dataclass
class EngineHooks:
    """Plain callbacks; the GUI adapts these onto queued Qt signals later."""

    on_node_status: list[Callable[[str, NodeMetrics], None]] = field(default_factory=list)
    on_outputs: list[Callable[[str, dict[str, Any]], None]] = field(default_factory=list)
    on_report: list[Callable[[RunReport], None]] = field(default_factory=list)

    def _fire(self, callbacks: list, *args: Any) -> None:
        for cb in callbacks:
            try:
                cb(*args)
            except Exception:  # hooks must never break the engine
                log.exception("engine hook raised")


class ExecutionService:
    def __init__(
        self,
        graph: Graph,
        settings: EngineSettings | None = None,
        resources: Resources | None = None,
    ):
        self.graph = graph
        self.settings = settings or EngineSettings()
        self.resources = resources or Resources()
        self.cache = OutputCache(self.settings.cache_budget_bytes)
        self.hooks = EngineHooks()

        self._instances: dict[str, Node] = {}
        self._setup_done: set[str] = set()
        self._state: dict[str, dict[str, Any]] = {}
        self._published: dict[tuple[str, str], Any] = {}
        self._ema: dict[str, float] = {}
        self._generation = 0
        self._pool: ThreadPoolExecutor | None = None

        graph.add_listener(GraphListener(on_topology=self._on_topology))

    # ---- public API --------------------------------------------------------
    def run(
        self,
        observed: Iterable[str] | None = None,
        *,
        armed: Iterable[str] = (),
        token: CancellationToken | None = None,
        mode: str = "interactive",
    ) -> RunReport:
        """Bring every observed/armed node up to date; blocking.

        ``observed``: node ids whose outputs someone watches (viewers).
        ``armed``: side-effect node ids allowed to execute this run.
        """
        t0 = time.perf_counter()
        self._generation += 1
        report = RunReport(generation=self._generation, mode=mode)

        armed_set = {n for n in armed if n in self.graph.nodes}
        observed_set = {n for n in (observed or ()) if n in self.graph.nodes}
        targets = observed_set | armed_set
        if not targets:
            report.wall_ms = (time.perf_counter() - t0) * 1000
            report.cache = self.cache.stats()
            return report

        demand = self.graph.ancestors(targets) | targets
        order = self.graph.topo_order(demand)

        # Dependency bookkeeping restricted to the demand closure.
        producers: dict[str, set[str]] = {}
        consumers: dict[str, set[str]] = {nid: set() for nid in demand}
        for nid in demand:
            prods = {e.src[0] for e in self.graph.in_edges(nid) if e.src[0] in demand}
            producers[nid] = prods
            for p in prods:
                consumers[p].add(nid)
        remaining = {nid: len(producers[nid]) for nid in demand}

        fps: dict[str, str | None] = {}
        values: dict[str, dict[str, Any]] = {}
        failed: set[str] = set()
        finalized: set[str] = set()
        ready: deque[str] = deque(n for n in order if remaining[n] == 0)
        in_flight: dict[Future, tuple[str, str, bool]] = {}  # fut -> (nid, fp, use_cache)

        def finalize(nid: str, metrics: NodeMetrics) -> None:
            finalized.add(nid)
            report.nodes[nid] = metrics
            self.hooks._fire(self.hooks.on_node_status, nid, metrics)
            for consumer in consumers[nid]:
                remaining[consumer] -= 1
                if remaining[consumer] == 0:
                    ready.append(consumer)

        def publish(nid: str, fp: str | None, outputs: dict[str, Any]) -> None:
            fps[nid] = fp
            values[nid] = outputs
            for port, value in outputs.items():
                self._published[(nid, port)] = value
            self.hooks._fire(self.hooks.on_outputs, nid, outputs)

        def dispatch(nid: str) -> None:
            inst = self.graph.nodes[nid]
            node_cls = inst.spec.node_class

            if token and token.cancelled:
                finalize(nid, NodeMetrics(NodeStatus.CANCELLED))
                return
            if producers[nid] & failed:
                finalize(nid, NodeMetrics(NodeStatus.BLOCKED))
                failed.add(nid)
                return

            issue = self._config_issue(inst)
            if issue:
                failed.add(nid)
                report.errors.append(NodeError(nid, issue))
                finalize(nid, NodeMetrics(NodeStatus.CONFIG_ERROR, error=issue))
                return

            input_fps = collect_input_fps(self.graph, nid, fps)
            if input_fps is None:  # producer published nothing usable
                failed.add(nid)
                finalize(nid, NodeMetrics(NodeStatus.BLOCKED))
                return
            fp = node_fingerprint(inst, input_fps, self.resources.base_dir)

            if node_cls.side_effect and nid not in armed_set:
                fps[nid] = None  # consumers of an unarmed sink are blocked
                finalize(nid, NodeMetrics(NodeStatus.SKIPPED))
                return

            use_cache = node_cls.cacheable and not node_cls.side_effect and not node_cls.stateful
            if use_cache:
                cached = self.cache.get(fp)
                if cached is not None:
                    publish(nid, fp, cached)
                    ema = self._ema.get(nid)
                    finalize(nid, NodeMetrics(
                        NodeStatus.CACHED, ema_ms=ema, cache_hit=True,
                        out_bytes=_total_bytes(cached)))
                    return

            try:
                input_values = self._assemble_inputs(inst, values)
            except CVFlowError as exc:
                failed.add(nid)
                report.errors.append(NodeError(nid, str(exc), type(exc).__name__))
                finalize(nid, NodeMetrics(NodeStatus.ERROR, error=str(exc)))
                return

            if self._pool_workers() == 0:
                result = _guarded(self._execute_node, nid, inst, input_values, token)
                complete(nid, fp, use_cache, result)
            else:
                fut = self._ensure_pool().submit(
                    _guarded, self._execute_node, nid, inst, input_values, token)
                in_flight[fut] = (nid, fp, use_cache)

        def complete(nid: str, fp: str, use_cache: bool, result: "_ExecResult") -> None:
            if result.error is not None:
                failed.add(nid)
                report.errors.append(result.error)
                finalize(nid, NodeMetrics(NodeStatus.ERROR, ms=result.ms,
                                          error=result.error.message))
                return
            outputs = result.outputs or {}
            if use_cache:
                self.cache.put(fp, outputs)
            publish(nid, fp, outputs)
            alpha = self.settings.ema_alpha
            self._ema[nid] = (alpha * result.ms + (1 - alpha) * self._ema[nid]
                              if nid in self._ema else result.ms)
            finalize(nid, NodeMetrics(NodeStatus.OK, ms=result.ms,
                                      ema_ms=self._ema[nid],
                                      out_bytes=_total_bytes(outputs)))

        while ready or in_flight:
            while ready:
                dispatch(ready.popleft())
            if in_flight:
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for fut in done:
                    nid, fp, use_cache = in_flight.pop(fut)
                    complete(nid, fp, use_cache, fut.result())

        for nid in order:  # anything never reached (cancellation mid-run)
            if nid not in finalized:
                report.nodes[nid] = NodeMetrics(NodeStatus.CANCELLED)

        # Pin what viewers are looking at; unpin the rest (docs/02 §3.2).
        self.cache.set_pinned({fps[n] for n in observed_set
                               if fps.get(n) is not None})

        report.wall_ms = (time.perf_counter() - t0) * 1000
        report.cache = self.cache.stats()
        self.hooks._fire(self.hooks.on_report, report)
        return report

    def get_output(self, node_id: str, port: str | None = None) -> Any:
        """Last published value(s) for a node — what viewers/CLI read."""
        if port is not None:
            return self._published.get((node_id, port))
        return {p: v for (n, p), v in self._published.items() if n == node_id}

    def close(self) -> None:
        for nid, node_obj in self._instances.items():
            inst = self.graph.nodes.get(nid)
            if inst is None:
                continue
            try:
                node_obj.teardown(self._bare_ctx(inst))
            except Exception:
                log.exception("teardown failed for %s", nid)
        self._instances.clear()
        self._setup_done.clear()
        if self._pool:
            self._pool.shutdown(wait=True)
            self._pool = None

    # ---- internals -------------------------------------------------------
    def _pool_workers(self) -> int:
        return max(0, self.settings.workers)

    def _ensure_pool(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=self._pool_workers(), thread_name_prefix="cvflow-worker")
        return self._pool

    def _instance(self, inst: NodeInstance) -> Node:
        node_obj = self._instances.get(inst.id)
        if node_obj is None:
            node_obj = inst.spec.node_class()
            self._instances[inst.id] = node_obj
        return node_obj

    def _bare_ctx(self, inst: NodeInstance) -> ExecutionContext:
        return ExecutionContext(
            node_id=inst.id, spec=inst.spec, params=inst.params,
            resources=self.resources, state=self._state.setdefault(inst.id, {}))

    def _config_issue(self, inst: NodeInstance) -> str | None:
        """Pre-execution validation: required inputs wired, params coherent."""
        for decl in inst.spec.inputs:
            if decl.optional or decl.variadic:
                continue
            if self.graph.edge_into(inst.id, decl.name) is None:
                return f"required input {decl.name!r} is not connected"
        try:
            issues = self._instance(inst).validate(dict(inst.params))
        except Exception as exc:  # a broken validate() is a config error
            return f"validate() raised: {exc}"
        for issue in issues:
            if issue.level == "error":
                return issue.message
        return None

    def _assemble_inputs(
        self, inst: NodeInstance, values: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        from cvflow.core.types.base import runtime_check

        assembled: dict[str, Any] = {}
        for decl in inst.spec.inputs:
            if decl.variadic:
                collected = []
                for e in self.graph.edges:
                    if e.dst == (inst.id, decl.name):
                        v = values[e.src[0]][e.src[1]]
                        collected.append(e.coercion.fn(v) if e.coercion else v)
                assembled[decl.name] = collected
                continue
            edge = self.graph.edge_into(inst.id, decl.name)
            if edge is None:
                assembled[decl.name] = None
                continue
            value = values[edge.src[0]].get(edge.src[1])
            if edge.coercion is not None and value is not None:
                value = edge.coercion.fn(value)
            problem = runtime_check(value, decl.dtype) if value is not None else None
            if problem:
                raise NodeExecutionError(f"input {decl.name!r}: {problem}")
            assembled[decl.name] = value
        return assembled

    def _execute_node(
        self,
        nid: str,
        inst: NodeInstance,
        input_values: dict[str, Any],
        token: CancellationToken | None,
    ) -> tuple[dict[str, Any], float]:
        node_obj = self._instance(inst)
        ctx = ExecutionContext(
            node_id=nid, spec=inst.spec, inputs=input_values, params=inst.params,
            resources=self.resources, state=self._state.setdefault(nid, {}),
            token=token)
        if nid not in self._setup_done:
            node_obj.setup(ctx)
            self._setup_done.add(nid)
        t0 = time.perf_counter()
        node_obj.process(ctx)
        ms = (time.perf_counter() - t0) * 1000
        return ctx.outputs.collect(), ms

    def _on_topology(self) -> None:
        for nid in list(self._instances):
            if nid not in self.graph.nodes:
                inst_obj = self._instances.pop(nid)
                self._setup_done.discard(nid)
                self._state.pop(nid, None)
                try:
                    inst_obj.teardown(None)  # type: ignore[arg-type]
                except Exception:
                    log.exception("teardown failed for removed node %s", nid)


# ---- worker-side helpers ---------------------------------------------------


@dataclass
class _ExecResult:
    outputs: dict[str, Any] | None = None
    ms: float = 0.0
    error: NodeError | None = None


def _guarded(fn: Callable, nid: str, *args: Any) -> _ExecResult:
    """Run one node; convert any exception into a NodeError record."""
    t0 = time.perf_counter()
    try:
        outputs, ms = fn(nid, *args)
        return _ExecResult(outputs=outputs, ms=ms)
    except (NodeExecutionError, ParamError) as exc:
        return _ExecResult(ms=(time.perf_counter() - t0) * 1000,
                           error=NodeError(nid, str(exc), type(exc).__name__,
                                           traceback.format_exc()))
    except Exception as exc:
        return _ExecResult(ms=(time.perf_counter() - t0) * 1000,
                           error=NodeError(nid, f"{type(exc).__name__}: {exc}",
                                           type(exc).__name__, traceback.format_exc()))


def _total_bytes(outputs: dict[str, Any]) -> int:
    from cvflow.core.types.base import nbytes_of

    return sum(nbytes_of(v) for v in outputs.values())
