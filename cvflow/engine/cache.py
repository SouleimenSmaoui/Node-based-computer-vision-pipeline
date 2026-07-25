"""Fingerprints and the byte-budgeted output cache (docs/02 §3).

Fingerprint = BLAKE2b over (type id, version, canonical params, external state,
input fingerprints + coercion labels). Merkle-style: equal fingerprints imply
equal results for pure nodes, with zero pixel hashing.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from cvflow.core.graph import Graph, NodeInstance
from cvflow.core.types.base import nbytes_of
from cvflow.engine.profiling import CacheStats


def node_fingerprint(
    inst: NodeInstance,
    input_fps: list[tuple[str, Any, str]],
    base_dir: str | None,
    params: dict[str, Any] | None = None,
) -> str:
    """``input_fps``: (port_name, upstream fingerprint hex | None, coercion label).

    ``params``: a coherent snapshot of the instance's params. The caller must
    pass the *same* dict here and to execution — reading ``inst.params`` twice
    at different times lets a concurrent GUI param edit land in between, so the
    node executes with new values but caches under the old fingerprint. That
    entry then serves a wrong image whenever the user returns to the old value
    (slider back, or undo). Defaults to a live read for callers outside a run.
    """
    spec = inst.spec
    values = dict(inst.params) if params is None else params
    payload = {
        "t": spec.type_id,
        "v": spec.version,
        "p": {p.name: p.to_json(values.get(p.name)) for p in spec.params},
        "x": spec.node_class.external_state(values, base_dir),
        "i": input_fps,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(blob.encode("utf-8"), digest_size=20).hexdigest()


def collect_input_fps(
    graph: Graph, node_id: str, fps: dict[str, str | None]
) -> list[tuple[str, Any, str]] | None:
    """Build the input part of a node's fingerprint from already-computed
    upstream fingerprints. Returns None if any connected producer has no
    fingerprint (errored/blocked) — the node cannot be fingerprinted or run."""
    inst = graph.nodes[node_id]
    out: list[tuple[str, Any, str]] = []
    for decl in inst.spec.inputs:
        if decl.variadic:
            entries = []
            for e in graph.edges:
                if e.dst == (node_id, decl.name):
                    fp = fps.get(e.src[0])
                    if fp is None:
                        return None
                    entries.append([f"{e.src[0]}.{e.src[1]}", fp,
                                    e.coercion.label if e.coercion else ""])
            out.append((decl.name, entries, ""))
            continue
        edge = graph.edge_into(node_id, decl.name)
        if edge is None:
            out.append((decl.name, None, ""))
            continue
        fp = fps.get(edge.src[0])
        if fp is None:
            return None
        out.append((decl.name, f"{edge.src[1]}:{fp}",
                    edge.coercion.label if edge.coercion else ""))
    return out


@dataclass
class _Entry:
    outputs: dict[str, Any]
    nbytes: int


class OutputCache:
    """LRU keyed by fingerprint, accounted in bytes, with pinning.

    Pinned entries (currently displayed/observed) are never evicted, so a
    viewer can't go blank because of memory pressure (docs/02 §3.2).
    """

    def __init__(self, budget_bytes: int = 2 * 1024**3):
        self.budget_bytes = budget_bytes
        self._entries: "OrderedDict[str, _Entry]" = OrderedDict()
        self._pinned: set[str] = set()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, fp: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(fp)
            if entry is None:
                self._misses += 1
                return None
            self._entries.move_to_end(fp)
            self._hits += 1
            return entry.outputs

    def put(self, fp: str, outputs: dict[str, Any]) -> None:
        size = sum(nbytes_of(v) for v in outputs.values())
        with self._lock:
            self._entries[fp] = _Entry(outputs, size)
            self._entries.move_to_end(fp)
            self._evict_over_budget()

    def _evict_over_budget(self) -> None:
        used = sum(e.nbytes for e in self._entries.values())
        if used <= self.budget_bytes:
            return
        for fp in list(self._entries):
            if used <= self.budget_bytes:
                break
            if fp in self._pinned:
                continue
            used -= self._entries.pop(fp).nbytes
            self._evictions += 1

    def set_pinned(self, fps: set[str]) -> None:
        with self._lock:
            self._pinned = set(fps)
            self._evict_over_budget()

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                bytes_used=sum(e.nbytes for e in self._entries.values()),
                budget_bytes=self.budget_bytes,
                entries=len(self._entries),
                evictions=self._evictions,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
