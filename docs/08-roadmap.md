# 08 — Development Roadmap: MVP → Industrial Grade

Assumption for estimates: **one senior Python/Qt developer, full-time** (you). With a
second developer, phases 1–2 compress roughly 35 % (GUI and engine parallelize well; the
core model does not — build it first, together).

Guiding rule: **every phase ends with something you use for real work**, because the
fastest way to design a prototyping tool is to prototype with it (dogfooding gates below).

---

## Phase 0 — Headless foundations (weeks 1–2)

Scope: `core` + `engine` + 5 nodes + CLI. **No GUI.**

- Graph model, descriptor-based `Node`/`ParamSpec`/`PortSpec`, registry, type system with
  `ImageBuffer` + coercion checks.
- Scheduler with topo order, fingerprint cache, dirty/demand closures, worker pool,
  cancellation. RunReport.
- Nodes: Load Image, To Gray, Gaussian Blur, Canny, Save Image.
- `cvflow run wf.json --set n7.kernel=9 --out out.png` + `cvflow validate`.
- Test rig: unit tests for scheduler/cache invariants (the *hard* bugs live here; catch
  them before a GUI obscures them), node conformance sweep, benchmark harness pinning N1.

**Exit criteria:** a JSON-defined 5-node pipeline runs headless; re-running with one
param changed executes only the affected suffix (assert via report); 1080p Gaussian+Canny
chain < 25 ms warm.

## Phase 1 — MVP (weeks 3–10)

The MVP answers exactly one question: *is tuning a CV pipeline in this tool decisively
faster than editing a script?* Everything that doesn't serve that question is out.

**In scope**

- App shell: main window, docking, dark theme, palette with search + Tab quick-add,
  node-editor adapter (badges, wire colors, dependency highlight), undo/redo.
  *(Update 2026-07-07: built as a bespoke `QGraphicsView` editor rather than
  NodeGraphQt — Python-3.14 compatibility, docs/01 §7.3.)*
- Auto-generated inspector for all ParamSpec widgets incl. RangeParam and pick-in-viewer
  RectParam.
- Interactive engine loop wired end-to-end: debounce, supersession, incremental cache,
  status badges, timing labels, status-bar totals.
- Viewer A/B: GL canvas, zoom/pan/probe, channel isolation, float normalization,
  contour/box/mask overlays, 2-pane linked compare.
- ~35 built-in nodes (the list in docs/01 §5 folder tree: io/color/filters/edges/
  threshold/morphology/geometry/analysis/draw/util/script). Video File node in *seekable
  scrub* mode (frame slider) — live streaming is Phase 2.
- Persistence v1 (save/load/autosave/recovery), example workflows, Errors panel,
  basic profiler table.
- Custom Script node (editor dialog, declared ports, inline tracebacks).
- CI: Windows + Linux, headless suite + pytest-qt smoke + golden images + perf gate.

**Explicitly out (deferred, with phase):** live webcam/RTSP (2), batch runner UI (2),
proxy mode (2), plugin hot-reload UX (2), multi-viewer >2 (2), subgraphs (3), GPU (3),
ML nodes (3), installer (2 — MVP runs from `pip install -e .`).

**Exit criteria (dogfood gate):** rebuild three of your real past experiments in CVFlow;
each must be faster end-to-end than the script version, param-to-pixel p95 < 100 ms on
1080p; save/reopen restores graph + viewers exactly; kill -9 during edit loses < 60 s of
work.

> **Progress (2026-07-25).** Node count is **33 of ~35**; the five outstanding
> (connected components, Hough lines/circles, template match, bounding boxes,
> statistics) are blocked on one type-design decision, not on effort — see
> `cvflow/nodes/README.md`.
>
> **Param-to-pixel is now measured rather than estimated: p50 38 ms, p95 48 ms,
> max 53 ms at 1080p**, against the 100 ms budget above. `cvflow/app/latency.py`
> times inspector-edit → viewer-pixmap with both ends on the GUI thread, so the
> 30 ms debounce, queued signal delivery and repaint are *inside* the number —
> engine timings alone would have flattered it. Caveat: measured offscreen, so
> compositing and vsync are excluded; re-confirm on a real display before ticking
> this criterion.
>
> Still open on this gate: the three dogfood rebuilds (the choice of experiments
> should drive which remaining nodes get built first), viewer-state restore on
> open, and kill -9 recovery.

## Phase 2 — Beta: streams, batch, polish (weeks 11–18)

- StreamExecutor: webcam + video-file live mode + RTSP (PyAV); FPS/drop HUD; stateful-node
  contract; param tuning on live streams; Save Video with lossless record queue.
- Batch over Image Folder: dialog, progress, per-item error policy, CSV/JSON sinks,
  results table; CLI parity (`cvflow run --batch`).
- Proxy-resolution preview; thumbnail-on-node option; multi-view 2×2 + wipe compare.
- Plugin DX: user-dir hot reload, `cvflow plugin new` scaffold, plugin failures panel,
  "Export script node as plugin".
- Profiler v2: EMA columns, heat overlay, cache hit-rates; data inspector panel.
- Packaging: PyInstaller builds + signed Windows installer; settings `cvflow.toml`;
  light theme; first external beta users (2–3 colleagues).

**Exit criteria:** 30 min of 1080p webcam streaming with live retuning, zero UI freezes
> 16 ms (instrumented), bounded memory; a colleague installs from the installer and
builds a working pipeline without help in < 30 minutes.

## Phase 3 — Industrial grade (weeks 19–32+)

- **Industrial I/O:** GenICam via Harvesters (+ a vendor reference plugin, e.g. Basler
  pypylon), trigger modes, pixel-format handling (Mono8/12, Bayer→BGR), camera parameter
  panel; RTSP hardening (reconnect policies).
- **ML nodes (per docs/11):** ONNX Runtime detect/segment/classify nodes, ModelManager
  (download/hash-verify/cache), RapidOCR node, tracking (ByteTrack-style on
  `Detections`), device selection UI; `cvflow[ml]` extra.
- **Performance lane:** opt-in process pool with shared-memory arrays for Python-heavy
  nodes; disk spill tier for expensive caches; optional CuPy-accelerated node pack.
- **Composites/subgraphs** with promoted params (team macro libraries).
- **Run-history SQLite** + profiler trends; crash reporting (opt-in, local dump first).
- **Hardening:** soak tests (24 h stream), memory-leak CI (tracemalloc snapshots),
  golden-image suite across OpenCV versions, plugin API v1.0 freeze + semver policy,
  user manual + node reference generated from NodeSpec docs.
- **Option, only if NodeGraphQt limits bite** (inline previews, >500-node perf): execute
  the planned `GraphViewPort` swap to a bespoke QGraphicsView editor (budget: 4–6 weeks,
  isolated by the adapter — docs/01 §7.3).

**Industrial-grade definition (checklist):** GenICam camera to annotated overlay at
camera rate with frame-drop accounting · 24 h unattended stream without leak or crash ·
batch of 10k images with resumable error report · installer + silent-install flag for IT ·
plugin API frozen at 1.0 with migration notes · every built-in node documented with
examples · recovery from kill -9 < 60 s data loss · perf budgets enforced in CI.

## Sequencing rationale

- **Engine before GUI** (Phase 0): scheduler/cache correctness is the highest-risk,
  highest-value logic; it must be testable without pixels on screen, and its API shapes
  the GUI controllers — not vice versa.
- **Stills before streams:** interactive still-image tuning exercises 100 % of the
  cache/incremental machinery with 10 % of the threading complexity; streaming reuses a
  proven plan compiler.
- **ML last:** DL nodes are *just nodes* by design (docs/11); shipping them early would
  drag heavy dependencies into every earlier debugging session while the substrate is
  still moving.
- **Packaging at beta, not MVP:** installers are pure friction while the only user has a
  dev environment; they become mandatory the day a second user exists.
