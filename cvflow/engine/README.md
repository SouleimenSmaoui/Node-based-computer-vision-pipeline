# cvflow.engine — execution

Demand-driven, fingerprint-cached, parallel execution of a `Graph`.
**May import:** `cvflow.core` only. No Qt, no cv2 in engine logic.

| File | Contents |
|---|---|
| `executor.py` | `ExecutionService.run(observed, armed)` — demand closure → topo order → per-node fingerprint → cache hit or worker dispatch; error isolation (ERROR → descendants BLOCKED, siblings continue); side-effect arming; `EngineSettings`, `EngineHooks` |
| `cache.py` | `node_fingerprint` (BLAKE2b Merkle: type+version+params+external_state+input fps — no pixel hashing), `OutputCache` (byte-budgeted LRU + pinning) |
| `context.py` | `ExecutionContext` (the only world a node sees), `Outputs` validator, `Resources` (base_dir…), `CancellationToken` |
| `profiling.py` | `RunReport`, `NodeMetrics`, `NodeStatus`, `CacheStats` |

How incrementality works: params and external state (file mtime) are *inside* the
fingerprint, so any change is a cache miss exactly for the affected suffix — there is
no separate dirty set (STATUS.md deviation #1). `workers=0` executes inline
(deterministic, used by tests); default is a small thread pool (OpenCV releases the
GIL, so parallel branches are real).

Clients drive it like this (the GUI will do the same from a worker thread):

```python
svc = ExecutionService(graph, EngineSettings(), Resources(base_dir=...))
report = svc.run(observed=["canny"], armed=["save"])   # blocking
value = svc.get_output("canny", "edges")
```

Design: docs/02. Next here: `streaming.py` (Phase 2 — push mode, bounded latest-wins
queues, stateful-node sequencing); cancellation polling between nodes is implemented,
mid-node `ctx.is_cancelled()` adoption grows with long-running nodes.
