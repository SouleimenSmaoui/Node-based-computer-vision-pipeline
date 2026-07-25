# 01 — Software Architecture

This document defines the requirements, the architectural principles, the layered system
design, the module breakdown, the source folder structure, the data-flow architecture, and
the justification for every major technology decision.

---

## 1. Requirements

### 1.1 Personas

- **P1 — CV engineer (primary, the author of this spec).** Fluent in Python/OpenCV. Wants
  to *experiment faster*, not to avoid code forever. Will write custom nodes. Keyboard-heavy
  user; values latency, correctness, and inspectability over hand-holding.
- **P2 — Application/test engineer (secondary, industrial phase).** Runs and re-tunes
  existing workflows on the factory floor or lab bench; rarely writes nodes.

### 1.2 Functional requirements (condensed)

| ID | Requirement |
|---|---|
| F1 | Build pipelines by dragging typed nodes onto a canvas and connecting ports |
| F2 | ~35 built-in OpenCV nodes at MVP (I/O, color, filters, edges, threshold, morphology, contours, Hough, template matching, draw, script) |
| F3 | Live parameter tuning: widget change → automatic incremental re-execution → viewer update |
| F4 | Inspect the output of *any* node; compare multiple nodes side-by-side; zoom/pan/probe; geometry overlays |
| F5 | Inputs: single image, image folder, video file, webcam, RTSP, industrial camera (GenICam), generated data |
| F6 | Outputs: image, video, text, CSV, JSON, metrics, overlay renders |
| F7 | Save/load/export workflows as JSON (positions, connections, parameters, metadata) |
| F8 | User-defined nodes via a Python plugin API; no core modification, no fork |
| F9 | Debugging: per-node timing, profiling, error reporting at the failing node, data inspection, dependency visualization |
| F10 | Architecture admits future DL nodes (YOLO, SAM, OCR, pose, tracking) without structural change |

### 1.3 Non-functional requirements with target numbers

Targets make "fast" testable. These are engineering budgets, not marketing claims.

| ID | Requirement | Target |
|---|---|---|
| N1 | Param-to-pixel latency, typical 6-node pipeline, 1080p, warm cache | **< 100 ms** (p95) |
| N2 | Same, 20 MP industrial image with proxy preview enabled | < 150 ms while dragging; full-res on release |
| N3 | Streaming throughput, 1080p webcam, light pipeline | ≥ 30 FPS (best effort, frame-drop policy — see N4) |
| N4 | Real-time discipline | *Soft* real time: never block, never queue unboundedly; drop frames instead. Hard real time is explicitly out of scope for Python |
| N5 | Memory | Configurable cache budget (default 2 GB), byte-accounted LRU; app usable on 16 GB machines with 20 MP pipelines |
| N6 | GUI responsiveness | GUI thread never executes pipeline work; no operation may freeze the UI > 16 ms |
| N7 | Startup | < 3 s to interactive window (heavy ML imports must be lazy) |
| N8 | Reliability | A failing node never crashes the app; autosave journal recovers unsaved graphs after a crash |
| N9 | Portability | Windows first (primary user platform), Linux and macOS supported by CI from MVP onward |
| N10 | Plugin API stability | Semantic versioning of the SDK from v1.0; deprecations live ≥ 2 minor versions |

### 1.4 Non-goals (explicit, to control scope)

- Not a distributed/cloud execution platform (Roboflow Workflows already exists for that niche).
- Not a model-training tool — inference only.
- Not a general-purpose programming environment — loops/branching beyond Switch/ForEach-folder
  patterns are deferred; the escape hatch is the Custom Script node.
- No hard real-time guarantees (see N4).
- Plugin sandboxing is not a security boundary (plugins are trusted code — see docs/09 risks).

---

## 2. Architectural principles

These six principles drive every decision below. When in doubt during implementation,
they are the tiebreakers.

**A1 — Headless core.** The graph model, type system, engine, persistence, and all nodes
form a pure-Python package with **zero Qt imports**. The GUI is one client of that core;
the CLI is another; a future REST server is a third. *Why:* testability (engine tests run
in CI without a display server), batch/headless execution comes for free, and GUI framework
churn can never hold the engine hostage. This is the single most important decision in the
design.

**A2 — Declarative nodes.** A node *declares* its ports and parameters as class attributes
(descriptor pattern, like Django/SQLAlchemy models). The framework derives — with no extra
code per node — the inspector UI, serialization, connection validation, default values,
undo entries, and documentation stubs. *Why:* every imperative "register your widgets"
API in comparable tools turns into N copies of subtly different boilerplate; declarative
specs are introspectable data, and 90 % of framework features fall out of introspection.

**A3 — Pull-based, fingerprint-cached, incremental evaluation.** Execution is driven by
*observed* outputs (open viewers, explicitly armed sinks). The engine pulls their transitive
dependencies, executing only nodes whose **fingerprint** (node type + version + parameters +
input fingerprints, Merkle-style) is not in the cache. *Why:* this is exactly the
"only affected downstream nodes re-execute" requirement, it never computes unobserved
branches, and fingerprints avoid hashing pixel data (cheap identity propagation). Full
design in docs/02.

**B4 — Typed dataflow.** Ports carry semantic types (`Image[GRAY8]`, `Contours`,
`Detections`), not bare `ndarray`. Connections are validated at connect time; cheap lossless
coercions are automatic, lossy ones require an explicit node. *Why:* "is this BGR or RGB,
binary or gray?" is the #1 silent bug class in OpenCV code; the type system turns it into
an immediate, visual error. Full design in docs/03.

**A5 — Plugins are not special.** Built-in nodes use the public plugin API exclusively.
*Why:* this is the only reliable way to keep a plugin API honest and complete — if the
core team needs a private hook, plugin authors needed it too.

**A6 — Everything observable.** Every execution produces a structured report: per-node
wall time, cache hit/miss, output sizes, errors with tracebacks. The GUI renders these
(badges, heat overlay, profiler table); the CLI prints them. *Why:* a prototyping tool's
job is insight, and "why is this slow / wrong" is half of prototyping.

---

## 3. Layered architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                               │
│  ┌──────────────────────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │ Desktop app (PySide6)        │  │ CLI runner    │  │ (future)    │  │
│  │ graph editor · inspector ·   │  │ run/validate/ │  │ REST/headless│ │
│  │ viewers · profiler · console │  │ batch         │  │ service     │  │
│  └──────────────┬───────────────┘  └───────┬───────┘  └──────┬──────┘  │
├─────────────────┼──────────────────────────┼─────────────────┼─────────┤
│  APPLICATION SERVICES (no Qt)              │                           │
│  ┌────────────────┐ ┌───────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │ SessionService │ │ Persistence   │ │ PluginLoader │ │ ModelMgr   │  │
│  │ (open graphs,  │ │ (JSON schema, │ │ (discovery,  │ │ (weights   │  │
│  │ undo journal)  │ │ migrations)   │ │ versioning)  │ │ cache)     │  │
│  └────────────────┘ └───────────────┘ └──────────────┘ └────────────┘  │
├────────────────────────────────────────────────────────────────────────┤
│  EXECUTION ENGINE (no Qt)                                              │
│  Scheduler (topo + dirty closure) · Fingerprint cache (LRU, byte-      │
│  budgeted) · InteractiveExecutor (pull, debounced, cancellable) ·      │
│  StreamExecutor (push, frame-dropping) · Profiler · ErrorCollector     │
├────────────────────────────────────────────────────────────────────────┤
│  CORE MODEL (no Qt, no engine deps)                                    │
│  Graph · NodeInstance · Edge · NodeSpec · Port · ParamSpec ·           │
│  Type system (ImageBuffer, Geometry, Detections, Tensor…) · Registry   │
├────────────────────────────────────────────────────────────────────────┤
│  NODE PACKS (import only the public SDK)                               │
│  builtin: io · color · filters · edges · threshold · morphology ·      │
│  contours · features · geometry · draw · analysis · script             │
│  plugins: user folder · pip entry points (cvflow.nodes)                │
└────────────────────────────────────────────────────────────────────────┘
```

### Import rules (enforced by CI lint)

| Package | May import |
|---|---|
| `cvflow.core` | stdlib, numpy, cv2 only |
| `cvflow.engine` | `core` |
| `cvflow.nodes.*` and external plugins | `cvflow.sdk` **only** (the public API facade) |
| `cvflow.io`, `cvflow.plugins`, `cvflow.services` | `core`, `engine` |
| `cvflow.app` (Qt) | everything |
| `cvflow.cli` | everything except `app` |

*Why an SDK facade (`cvflow.sdk`)?* Plugin authors import one stable module
(`from cvflow.sdk import node, ImageIn, IntParam, …`). Internals can be refactored freely;
only `sdk` carries the semver compatibility promise (N10).

---

## 4. Module breakdown

| Module | Responsibility | Key classes (see docs/07 for diagrams) |
|---|---|---|
| `core.graph` | Graph document: nodes, edges, groups; structural validation (cycle check, type check); change notifications via observer callbacks | `Graph`, `NodeInstance`, `Edge`, `GraphListener` |
| `core.node` | Node base class, declarative descriptor collection, lifecycle contract | `Node`, `NodeSpec`, `NodeMeta` |
| `core.ports` | Port descriptors and runtime port objects, variadic/optional ports | `InputPort`, `OutputPort`, `PortSpec` |
| `core.params` | Parameter descriptors (Int, Float, Enum, Bool, String, Path, Point, Range…), validation rules, widget hints | `ParamSpec` hierarchy |
| `core.types` | Data type registry, `ImageBuffer`, geometry/detection/tensor types, coercion matrix | `DataType`, `ImageBuffer`, `Detections`, … |
| `core.registry` | Node type registry: id → NodeSpec, versions, categories, search index | `NodeRegistry` |
| `engine.scheduler` | Dirty propagation, demand closure, topological order, ready-set dispatch | `Scheduler`, `ExecutionPlan` |
| `engine.cache` | Fingerprint computation, byte-budgeted LRU store, pinning | `Fingerprint`, `OutputCache` |
| `engine.executor` | Interactive (pull/debounce/cancel) and worker-pool execution | `ExecutionService`, `InteractiveExecutor`, `CancellationToken` |
| `engine.streaming` | Frame-driven push execution, bounded queues, drop policy, stateful-node sequencing | `StreamExecutor`, `StreamSource`, `FramePump` |
| `engine.context` | What a node sees while running: inputs, params, outputs, logging, cancellation, per-node persistent state | `ExecutionContext`, `NodeState` |
| `engine.profiling` | Timings, cache stats, run reports | `RunReport`, `NodeMetrics` |
| `io.workflow_json` | Serialize/deserialize graph ↔ JSON, schema validation, version migrations | `WorkflowSerializer`, `Migration` |
| `io.assets` | Relative-path asset resolution, project bundles (zip) | `AssetResolver` |
| `plugins.loader` | Discover builtin packs, entry points, user plugin dir; hot reload; failure isolation | `PluginLoader`, `PluginInfo` |
| `services.session` | Open documents, autosave journal, recent files, undo transcript (GUI-agnostic) | `SessionService` |
| `services.models` | (Phase 3) model weight download/cache/integrity | `ModelManager` |
| `sdk` | Public, semver-stable plugin authoring facade | re-exports |
| `app.*` | Qt GUI: main window, graph view adapter, inspector, viewers, palette, console, profiler, theme | see docs/05 |
| `cli` | `cvflow run`, `cvflow validate`, `cvflow nodes list`, batch processing | `main()` |

---

## 5. Folder structure

```
computer_vision_app/
├── pyproject.toml                  # single installable package; extras: [app], [ml], [camera]
├── README.md
├── docs/                           # this design documentation
├── cvflow/
│   ├── __init__.py
│   ├── sdk.py                      # ← the ONLY import surface for node authors
│   ├── core/
│   │   ├── graph.py
│   │   ├── node.py
│   │   ├── ports.py
│   │   ├── params.py
│   │   ├── registry.py
│   │   ├── errors.py
│   │   └── types/
│   │       ├── base.py             # DataType, registry, coercions
│   │       ├── image.py            # ImageBuffer, color spaces
│   │       ├── geometry.py         # Point, Line, Polygon, Contours, BBox, Mask, Keypoints
│   │       ├── detections.py       # Detections (boxes+scores+labels+masks+ids)
│   │       ├── tensor.py           # Tensor (layout, device)
│   │       └── scalars.py          # Text, Number, ListValue, DictValue
│   ├── engine/
│   │   ├── scheduler.py
│   │   ├── cache.py
│   │   ├── executor.py
│   │   ├── streaming.py
│   │   ├── context.py
│   │   └── profiling.py
│   ├── nodes/                      # built-in packs — import cvflow.sdk only
│   │   ├── io/        (load_image.py, image_folder.py, video_file.py, webcam.py,
│   │   │               save_image.py, save_video.py, csv_writer.py, json_writer.py)
│   │   ├── color/     (convert.py, split_merge.py, clahe.py, in_range.py)
│   │   ├── filters/   (gaussian.py, median.py, bilateral.py, box.py, unsharp.py)
│   │   ├── edges/     (canny.py, sobel.py, laplacian.py)
│   │   ├── threshold/ (global_threshold.py, adaptive.py)
│   │   ├── morphology/(morph.py)            # op dropdown: erode/dilate/open/close/…
│   │   ├── geometry/  (resize.py, crop_roi.py, rotate_flip.py, warp_affine.py,
│   │   │               perspective.py)
│   │   ├── analysis/  (find_contours.py, filter_contours.py, connected_components.py,
│   │   │               hough_lines.py, hough_circles.py, template_match.py,
│   │   │               measurements.py, statistics.py)
│   │   ├── features/  (orb.py, match_features.py)
│   │   ├── draw/      (draw_contours.py, draw_boxes.py, draw_text.py, overlay_mask.py,
│   │   │               blend.py)
│   │   ├── util/      (switch.py, math_op.py, display_text.py)
│   │   ├── script/    (custom_script.py)
│   │   └── ml/        (Phase 3: onnx_detect.py, onnx_segment.py, ocr.py, …)
│   ├── io/
│   │   ├── workflow_json.py
│   │   ├── migrations/             # one module per schema version bump
│   │   └── assets.py
│   ├── plugins/
│   │   ├── loader.py
│   │   └── api_version.py
│   ├── services/
│   │   ├── session.py
│   │   └── models.py
│   ├── app/                        # PySide6 — only package allowed to import Qt
│   │   ├── main.py                 # entry point: cvflow-app
│   │   ├── mainwindow.py
│   │   ├── controllers/            # mediate core↔widgets; own all engine callbacks
│   │   │   ├── graph_controller.py
│   │   │   ├── execution_controller.py   # debounce, run requests, result routing
│   │   │   └── session_controller.py
│   │   ├── graphview/              # NodeGraphQt adapter (swappable — see §7.3)
│   │   │   ├── adapter.py          # GraphViewPort interface implementation
│   │   │   ├── node_item_factory.py
│   │   │   └── badges.py           # status LEDs, timing labels, heat overlay
│   │   ├── inspector/              # auto-generated parameter panels
│   │   │   ├── panel.py
│   │   │   └── widgets.py          # ParamSpec → QWidget factory
│   │   ├── viewer/
│   │   │   ├── image_view.py       # zoom/pan/probe canvas (QGraphicsView+GL)
│   │   │   ├── overlays.py         # geometry → QGraphicsItem renderers
│   │   │   ├── viewer_panel.py     # toolbar, channel select, histogram
│   │   │   └── multi_view.py       # 1×1/1×2/2×2 linked grids
│   │   ├── palette/                # searchable node library
│   │   ├── console/                # log + error panel
│   │   ├── profiler/               # per-node metrics table
│   │   └── theme/                  # dark theme, icons, DPI handling
│   └── cli/
│       └── main.py                 # entry point: cvflow
├── plugins-examples/               # cookiecutter-style example plugin package
│   └── cvflow-plugin-example/
├── examples/workflows/             # shipped sample .cvflow.json files
└── tests/
    ├── core/  engine/  io/  nodes/         # headless — no Qt, run everywhere
    ├── app/                                # pytest-qt, GUI smoke tests
    └── golden/                             # golden-image regression data
```

*Why a single package with extras instead of a multi-repo split?* At this team size,
repo boundaries add release friction without architectural benefit; the import-rule lint
(§3) enforces the same discipline. Extras (`pip install cvflow[app]`, `[ml]`, `[camera]`)
keep the headless core installable on servers without Qt or torch.

---

## 6. Data-flow architecture

### 6.1 The value contract

1. **Outputs are immutable.** When a node publishes an output, the engine freezes it —
   for `ImageBuffer` this is literal: `array.setflags(write=False)`. A node needing to
   modify an input must copy (`buf.writable_copy()`). *Why:* immutability is what makes
   caching, multi-viewer display, and parallel branch execution safe without defensive
   copies everywhere. The numpy write-flag turns violations into immediate exceptions
   instead of heisenbugs.
2. **Values flow by reference.** No serialization between nodes; an edge hands over the
   Python object. A 20 MP image costs nothing to "send" to three consumers.
3. **Every published value carries a fingerprint** (see docs/02 §3) — identity without
   content hashing.
4. **Side effects are explicit.** Nodes that touch the outside world (Save Image, CSV
   Writer, serial/PLC output later) declare `side_effect = True` and only run when armed
   (manual Run, batch mode, or record mode) — never on a slider tick. *Why:* live tuning
   must be safe; nobody wants 400 PNGs written while dragging a sigma slider.

### 6.2 Interactive mode (still images) — the common loop

```
slider drag ──► ExecutionController (GUI)            engine thread(s)
   │ set param (coalesced undo)                          │
   │ debounce ~30 ms, cancel in-flight run               │
   └──► RunRequest{observed nodes} ──────────────► Scheduler:
                                                    dirty closure ∩ demand closure
                                                    topo order → ready set
                                                    workers: cache hit? skip : process()
        viewer/badge updates ◄── queued callbacks ── publish outputs + RunReport
```

Full mechanics, including cancellation and proxy-resolution preview: docs/02.

### 6.3 Streaming mode (video/camera)

A source thread pumps frames into a bounded latest-wins queue (size 2, drop-oldest); each
frame executes through the same compiled plan; stateful nodes (trackers, background
subtraction) are guaranteed sequential frame order. Recording switches the relevant sink
path to lossless/blocking semantics with an explicit "can't keep up" warning. Full design:
docs/02 §7.

### 6.4 Batch mode (image folder)

Batch = streaming with a finite source plus aggregation sinks (CSV/JSON collect per-frame
rows). Progress and per-image error tolerance (`skip & report` vs `abort`) are engine
options, surfaced in the GUI as a batch dialog and in the CLI as flags.

---

## 7. Technology decisions and alternatives considered

Each decision lists the realistic alternatives and why they lost. These were genuinely
weighed, not retro-fitted.

### 7.1 Desktop-native (Qt) vs web stack (Electron/Tauri + Python backend)

**Chosen: native desktop, PySide6.**

- The inner loop is *display a freshly computed 2–20 MP image within milliseconds*. A web
  UI must encode (PNG/JPEG/WebRTC) and ship every preview frame across a process/socket
  boundary; native Qt blits a numpy buffer into a GL texture in the same process. The
  latency budget (N1) is hard to meet over an encode hop, and trivial without it.
- Industrial cameras (GenICam producers, vendor SDKs) and webcams are native-process
  resources; a browser sandbox is an obstacle, not a feature, here.
- Single-user, often-offline (lab/factory) usage profile — the web's deployment and
  collaboration advantages don't apply. Roboflow Workflows already serves the cloud
  niche; we are deliberately the local/industrial complement.
- Cost: native UI development is slower than React, and distribution needs installers.
  Accepted; mitigated by Qt's mature docking/widgets and PyInstaller (docs/09 R7).

### 7.2 PySide6 vs PyQt6 vs Tkinter/Kivy/Dear PyGui

**Chosen: PySide6.**

- PyQt is GPL/commercial — a real constraint the moment this tool is used or distributed
  inside a company. PySide6 is LGPL and is *the Qt-official* binding. Identical API,
  zero functional sacrifice.
- Tkinter/Kivy can't deliver a professional docking IDE-style UI or a high-performance
  graphics canvas at this complexity. Dear PyGui is fast but immature for a long-lived
  professional tool (theming, accessibility, ecosystem).
- Qt specifically gives us: `QGraphicsView` (the standard substrate for node editors and
  image canvases), `QOpenGLWidget` (GPU image display), `QDockWidget` (pro layout),
  `QUndoStack` (undo done right), and qt-material/QSS theming.

### 7.3 Node editor: NodeGraphQt vs qtpynodeeditor vs pyqtgraph.flowchart vs Ryven vs custom

**Chosen: NodeGraphQt (MIT) behind a thin adapter interface; custom editor as a planned
possible successor.**

> **Update 2026-07-07 (Phase 1 build):** we shipped the *bespoke `QGraphicsView`
> editor* now rather than NodeGraphQt. Reason: the target runtime is Python 3.14,
> for which NodeGraphQt (and its superqt/qtawesome/Qt.py stack) has no verified
> support, while PySide6 6.11 ships an abi3 wheel that runs fine. This is R3
> (docs/09) realized early and resolved exactly as planned — the `GraphViewPort`
> seam held, so the GUI depends on **PySide6 alone**. The 4–6 week estimate below
> assumed feature-parity with NodeGraphQt; the Phase-1 editor is a leaner subset
> (pan/zoom, box-select, drag-connect with live type-check, Tab quick-add,
> palette drag-drop, status LEDs, coercion badges). Backdrops/reroutes/inline
> previews remain future work. `app/graphview/` is the adapter.

- NodeGraphQt is the most complete, actively used PySide6 node-canvas library: ports,
  reroutes, groups/backdrops, search tab-menu, serialization hooks, custom node widgets.
  Building an equivalent custom canvas is realistically 4–6 weeks that the MVP shouldn't
  spend.
- qtpynodeeditor (port of C++ QtNodes) is less maintained; pyqtgraph.flowchart is too
  basic visually; Ryven is an application rather than an embeddable canvas (and we have
  our own engine — we only need the *view*).
- **Risk control:** NodeGraphQt is effectively single-maintainer. Therefore the app talks
  to a `GraphViewPort` adapter interface (`add_node`, `connect`, `set_badge`,
  `on_node_moved`, …) and NodeGraphQt never leaks outside `app/graphview/`. If we outgrow
  it (inline node previews, heat overlays beyond what it allows) we implement the same
  interface on a bespoke `QGraphicsView` editor — an isolated, budgeted migration
  (roadmap Phase 3 option), not a rewrite.

### 7.4 Custom DAG engine vs Dask / Prefect / Airflow / Beam / ReactiveX

**Chosen: custom engine (~1.5–2 k LOC).**

- Those systems orchestrate *tasks* at second-to-minute scale with scheduling overheads
  of milliseconds-to-seconds per task and serialization between workers. Our unit of work
  is a 0.1–50 ms OpenCV call on a shared-memory array, re-triggered 30× per second by a
  slider — orchestrator overhead exceeds the work itself by orders of magnitude.
- None of them natively model our core semantics: fingerprint-memoized incremental
  re-evaluation of a *mutable interactive* graph + demand-driven pull from viewers +
  cancellation-on-supersede. We'd fight the framework to fake all three.
- The custom engine is small, dependency-free, and *is* the product's core IP. Risk of
  "custom = unmaintained science project" is mitigated by keeping it tiny, pure, and
  heavily unit-tested (it has no Qt and no cv2 in its own logic — it schedules callables).

### 7.5 OpenCV + NumPy as the processing substrate

Non-controversial: it is the requirement and the industry standard. Two load-bearing
facts shape the engine: OpenCV **releases the GIL** during native calls (real thread
parallelism for branches), and OpenCV's native channel order is **BGR**, which dictates
the canonical-BGR policy in docs/03 §3.

### 7.6 Why not build on napari / Ryven / existing tools

- **napari**: excellent *viewer* with a plugin ecosystem, but its model is layers +
  widgets, not dataflow graphs; retrofitting graph semantics fights its architecture. We
  borrow its ideas (GL canvas, layered overlays) instead.
- **HALCON/HDevelop, LabVIEW**: commercial, closed, and the *reason this product needs to
  exist* for OpenCV users.
- **Node-RED**: JS runtime, message-passing semantics, wrong substrate for numpy arrays.

### 7.7 JSON files vs database for persistence

**Chosen: JSON workflow files; optional SQLite later for run history only.**
Workflows are *documents*: users diff them, email them, commit them to git. A database
adds operational weight and kills diffability. SQLite enters in Phase 3 strictly for
append-only run/metrics history (docs/06 §6). 

### 7.8 GPU strategy

**Chosen: CPU-first; GPU via ONNX Runtime execution providers for ML, optional CuPy for
array math; `cv2.cuda` only as an advanced custom-build path.**
The honest constraint: stock `opencv-python` wheels ship **without CUDA**. Promising
GPU-accelerated classic CV would require custom OpenCV builds per platform — a packaging
tax that would dominate the project. ML inference, where GPU matters most, gets GPU
cleanly through `onnxruntime-gpu`. Full plan: docs/11 §5.

---

## 8. Cross-cutting concerns

- **Logging:** stdlib `logging` with per-subsystem loggers (`cvflow.engine`, …); GUI
  console subscribes via a handler; `rich` formatting in CLI. No third-party logging dep
  in core.
- **Errors:** exception taxonomy in `core.errors` (`GraphError`, `ConnectionTypeError`,
  `NodeExecutionError(node_id, cause, traceback)`, `PluginLoadError`). Engine converts
  node exceptions into per-node failure states; the app never sees a raw worker traceback
  except inside a report object.
- **Configuration:** `QSettings` for GUI state (window layout, theme); a `cvflow.toml`
  (platformdirs user-config location) for engine settings (cache budget, thread count,
  proxy resolution) so headless runs honor the same config.
- **i18n:** out of scope for MVP; all user-facing strings flow through one helper from
  day 1 so extraction stays possible.
- **Testing strategy:** unit (core/engine, no I/O), node conformance (every registered
  node is auto-tested for spec validity + smoke-run on synthetic images), golden-image
  regression for built-in nodes, pytest-qt smoke for GUI wiring, benchmark suite pinning
  N1/N3 budgets in CI.
