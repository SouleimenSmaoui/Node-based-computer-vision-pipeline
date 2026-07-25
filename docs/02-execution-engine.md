# 02 — Workflow Execution Engine

The engine answers one question fast: *given that something changed (a parameter, a
connection, a new frame), what is the minimum work needed to bring every observed output
up to date — without ever blocking the GUI?*

It is a pure-Python package (`cvflow.engine`) with **no Qt and no OpenCV dependencies in
its own logic** — it schedules opaque callables over typed values. That keeps it unit-
testable in milliseconds and reusable by GUI, CLI, and future server front-ends (principle
A1).

---

## 1. Graph model recap

- Directed acyclic graph. `Graph.add_edge` rejects cycles (incremental DFS check) and
  type-incompatible connections (docs/03 §6) *at edit time* — errors surface when the user
  draws the wire, not at run time.
- An **input port** has exactly one incoming edge (or zero if optional/defaulted); an
  **output port** fans out to any number of consumers. Variadic input ports (e.g., Blend,
  Merge Channels) accept an ordered list of edges.
- Each `NodeInstance` holds: stable `node_id` (UUID), `NodeSpec` reference (type id +
  version), parameter values, UI position, and runtime status.

## 2. Execution semantics: demand-driven pull

**Observed set** = nodes whose outputs someone is watching: open viewers, pinned
previews, plus (when armed) side-effect sinks. The engine computes the **demand closure**
(observed nodes + all transitive ancestors). Only that closure can ever execute.

**Dirty set**: editing a parameter, re-wiring, or replacing source data marks the node
dirty; dirtiness propagates to all descendants (cheap DFS over an adjacency index kept by
`Graph`).

**Execution plan** = demand closure ∩ (dirty nodes ∪ nodes with missing cache entries),
in topological order. Everything else is reused from cache.

*Why pull instead of push-everything?* It implements requirement "only affected
downstream nodes re-execute" *and* its dual that push misses: un-observed branches don't
execute at all. With 3 viewers open on a 40-node experimental graph, you pay only for the
3 visible paths. It also gives a crisp mental model: **what you see is exactly what ran**.

### 2.1 Scheduling within a run

```python
def build_plan(graph, observed, cache) -> ExecutionPlan:
    demand  = ancestors(observed) | observed
    pending = {n for n in demand if not cache.has(fingerprint(n))}
    return topo_order(pending)          # Kahn's algorithm, deterministic tiebreak

def run(plan, pool, token):
    indegree = remaining_pending_deps(plan)
    ready    = deque(n for n in plan if indegree[n] == 0)
    while pending and not token.cancelled:
        dispatch all `ready` nodes to pool          # parallel branches
        on completion: publish outputs → decrement consumers' indegree
                       → enqueue newly ready nodes
```

Independent branches run concurrently on a thread pool (default `min(4, cpu)` workers —
empirically, image pipelines saturate memory bandwidth before core count). OpenCV/NumPy
release the GIL, so this is real parallelism for native ops; pure-Python nodes simply
interleave. A per-node `parallel_unsafe = True` opt-out exists for nodes wrapping
non-thread-safe libraries.

## 3. Incremental execution: fingerprint caching

### 3.1 The fingerprint (Merkle identity, no pixel hashing)

```
fp(node) = H( node_type_id, node_version,
              canonical(params),
              [fp_of_upstream_output for each connected input] )
```

`H` = BLAKE2b over a canonical msgpack/JSON encoding. Source nodes fold in their external
identity: file path + mtime + size (Load Image), frame index (Video File), monotonic
frame counter (camera). 

**Why fingerprints, not content hashes:** hashing a 20 MP float image on every hop would
cost more than most node executions. Fingerprints are O(small) regardless of data size,
and equal fingerprints ⇒ equal results *by construction* (same code version, same params,
same inputs), provided nodes are pure — which the immutability contract (docs/01 §6.1)
and the `side_effect`/`stateful` flags make explicit. Nondeterministic nodes declare
`cacheable = False`.

### 3.2 The cache

- `OutputCache`: map `fingerprint → tuple(outputs)`, LRU ordered, **byte-accounted**
  (each value type reports `nbytes`); budget configurable, default **2 GB**.
- **Pinning:** values currently displayed in any viewer are pinned (never evicted while
  visible) — eviction must never blank a viewer.
- Eviction is wholesale per entry (all outputs of one node execution evicted together).
- Phase 3 option: disk spill tier (memory-mapped npy) for expensive-to-recompute nodes
  (ML inference), opt-in per node via `cache_priority`.

A cache hit costs a dict lookup; this is what makes dragging a slider on node 7 of 10
re-run only nodes 7–10 while 1–6 are free.

## 4. The interactive loop: debounce, cancellation, supersession

Slider drags emit value changes at 60–120 Hz; running the pipeline for each is wasteful
and induces queue lag. The `ExecutionController` (client side) implements:

1. **Debounce/coalesce — 30 ms.** A change starts (or restarts) a 30 ms timer; the run
   uses the *latest* values. 30 ms is below perception threshold but absorbs event bursts.
2. **Supersession.** Each run carries a generation number and a `CancellationToken`. A
   newer request cancels the in-flight run: the scheduler stops dispatching, and
   long-running nodes may poll `ctx.is_cancelled()` to abort mid-node. Stale results
   (generation < latest published) are discarded, never displayed — prevents the classic
   "slider released but image flickers through old values" artifact.
3. **At most one queued run.** If a run is executing and changes keep arriving, exactly
   one follow-up run is scheduled with final values (latest-wins; intermediates dropped).

### 4.1 Proxy resolution preview (industrial image sizes)

Meeting N2 (<150 ms while dragging a slider on a 20 MP image) is not possible for every
node chain at full resolution. Borrowing from film compositing tools (Nuke proxy mode):

- While a continuous widget is being dragged, the controller may request **proxy
  execution**: source nodes emit a downscaled image (default max edge 1280 px), the chain
  runs at proxy scale, and the viewer labels the result `PROXY`.
- On release, a full-resolution run replaces it.
- Scale-dependent parameters (kernel sizes in pixels) are *not* rescaled — proxies
  preview structure, full-res is the truth; the label makes this honest. Per-workflow
  toggle, off by default below 4 MP where full-res already meets the budget.

*Why this design:* it converts worst-case latency into a constant, preserves full-res
correctness semantics, and is entirely client-side policy — the engine just sees a
`scale` hint on the run request.

## 5. Execution context — what a node sees

```python
def process(self, ctx: ExecutionContext) -> None:
    img   = ctx.inputs.image            # typed value, read-only
    k     = ctx.params.kernel           # validated, defaulted
    ctx.ensure(img.space is ColorSpace.GRAY, "expects grayscale input")
    out   = cv2.GaussianBlur(img.data, (k, k), ctx.params.sigma)
    ctx.outputs.image = img.derive(out) # inherits space/meta, freezes array
```

`ExecutionContext` also provides: `ctx.log` (node-scoped logger), `ctx.progress(0..1)`
(long ops), `ctx.is_cancelled()`, `ctx.state` (persistent per-node dict for stateful
nodes — see §7.3), `ctx.frame` (index/timestamp in stream mode), `ctx.scale` (proxy
hint), and `ctx.resources` (shared handles, e.g. the ModelManager). Nodes never touch the
engine, the graph, or other nodes — the context is the entire world. *Why:* this boundary
is what makes nodes trivially unit-testable (`run_node()` harness, docs/04 §8) and lets
the engine change freely underneath.

## 6. Error semantics

- A raised exception inside `process()` is captured as
  `NodeError(node_id, exc_type, message, traceback, input_summary)`.
- The failing node gets status `ERROR`; its descendants in the plan become `BLOCKED`
  (skipped, marked, not failed); **independent branches continue** — one broken
  experimental branch must not kill the whole canvas.
- The run completes with a `RunReport` carrying all errors; the GUI shows a red badge on
  the node, the message in the console panel, and the traceback on demand.
- Validation errors (bad param combos detected by `Node.validate()`) surface *before*
  execution as amber badges — cheaper and earlier than runtime failure.

## 7. Streaming mode (video, webcam, RTSP, industrial cameras)

Interactive pull is wrong for live sources — frames *push*. The `StreamExecutor` reuses
the same plan/cache machinery with inverted drive:

### 7.1 Pipeline

```
SourceThread (camera grab loop)
   └─► BoundedQueue(maxsize=2, policy=DROP_OLDEST)      # latest-wins
         └─► FramePump: per frame → execute compiled plan (same workers)
               └─► publish to viewers (rate-limited to display refresh)
                   sinks honor record mode (§7.4)
```

- **Bounded queue, drop-oldest** is the load-shedding policy (N4): when processing is
  slower than capture, latency stays bounded (~2 frames) and the newest frame wins.
  Unbounded queues are the classic mistake — memory balloons while latency grows
  unboundedly.
- The plan is **compiled once** per graph edit (topo order, type checks, param snapshot
  layout), so per-frame overhead is dispatch only. Parameter tweaks during a live stream
  swap the param snapshot atomically between frames — live tuning on live video works.
- Caching is mostly bypassed per frame (every frame is new), but *static subgraphs* —
  branches not downstream of the source (e.g., a loaded template image being
  preprocessed) — keep full fingerprint caching. This falls out of the fingerprint design
  for free.

### 7.2 Sources

`StreamSource` interface: `open() / read() -> Frame | EOS / close()`, plus capability
metadata (seekable, fps, resolution). Implementations: `VideoFileSource` (cv2 /PyAV),
`WebcamSource` (cv2, DirectShow/MSMF on Windows), `RtspSource` (PyAV — cv2's RTSP
handling is too fragile), `GenICamSource` (Harvesters, Phase 3), vendor plugins
(e.g., pypylon) via the normal plugin system. Video files are also usable in
*interactive* mode as a seekable frame source (scrub slider on the node), which is the
MVP path before live streaming lands.

### 7.3 Stateful nodes

Trackers, background subtractors, temporal filters carry state across frames. They
declare `stateful = True`, which buys them: guaranteed sequential per-frame execution
(never parallelized across frames), `ctx.state` persistence between frames, a
`reset_state()` call on stream start/seek, and exclusion from output caching. *Why
explicit:* silent statefulness breaks caching and parallelism invariants; making it a
declared property lets the engine keep its guarantees and the UI mark such nodes (⟲ badge).

### 7.4 Recording

Save Video / CSV sinks in record mode switch their path to **lossless delivery**: a
dedicated writer thread with its own deep queue, and if it still can't keep up the UI
shows a sustained "dropping recorded frames" warning (or, optionally, backpressures the
source for file-based inputs where real time doesn't matter). Display can drop frames;
recordings shouldn't — different queues, different policies.

## 8. Threading model summary

| Thread | Owns | Never does |
|---|---|---|
| GUI (Qt main) | widgets, graph editing, run *requests* | execute nodes, file I/O |
| Engine dispatcher | plan building, ready-set bookkeeping | heavy compute |
| Worker pool (N≈4) | `node.process()` | touch Qt |
| Source threads (per stream) | camera/file grabbing | processing |
| Writer threads (per recording sink) | encoding/writes | processing |

Engine→GUI delivery: the engine exposes plain callback hooks (`on_node_status`,
`on_outputs`, `on_report`); the Qt `ExecutionController` adapts them onto queued signals
(thread-safe by Qt contract). The engine remains Qt-free; a CLI subscribes the same hooks
to print progress. GIL reality: native OpenCV releases it; a pathological pure-Python
node can serialize workers but can never block the GUI thread. Phase 3 adds an opt-in
**process pool** lane (with `multiprocessing.shared_memory` for zero-copy arrays) for
heavy Python-bound nodes.

## 9. Profiling & debugging instrumentation

Every run yields a `RunReport`:

```python
RunReport(
  generation=412, wall_ms=38.2, mode=INTERACTIVE,
  nodes={ "n7": NodeMetrics(status=OK, ms=11.4, ema_ms=12.1,
                            cache=MISS, out_bytes=6_220_800), ... },
  errors=[...], cache_stats=CacheStats(hits=5, misses=3, bytes=812e6, evictions=0))
```

Consumed by: node badges (status + last ms), the profiler table (sortable by EMA time —
EMA because single samples lie), the heat overlay (node tint ∝ share of pipeline time),
the status bar (total ms, FPS in stream mode), and `cvflow run --profile` in CI to catch
performance regressions. Dependency visualization (highlight ancestors/descendants of a
selected node, i.e. the demand/dirty closures) reads the same adjacency index the
scheduler uses — the debugger shows the literal truth of what would run.

## 10. Engine API surface (what clients call)

```python
svc = ExecutionService(graph, settings)
svc.set_observed({node_id: [port, ...]})        # viewers register demand
svc.notify_param(node_id)                        # → dirty propagation
svc.request_run(scale=None) -> generation        # debounced upstream by caller
svc.arm_sinks([node_ids]); svc.run_batch(...)    # explicit side effects
svc.start_stream(source_node); svc.stop_stream()
svc.hooks.on_outputs / on_node_status / on_report / on_stream_stats
```

Small on purpose: the GUI cannot reach into scheduling internals, which is what keeps
GUI and engine independently evolvable (and the engine honest about A1).
