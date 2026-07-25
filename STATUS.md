# STATUS — where the project stands and what comes next

> Keep this file truthful. Update it at the end of every work session.
> Last updated: **2026-07-25** (session 4 — repo under git; see Next steps)

## Phase position (see docs/08-roadmap.md)

**Phase 0 — headless foundations: ✅ COMPLETE.** All Phase 0 exit criteria met:

- [x] JSON-defined pipeline runs headless via `cvflow run` (demo: load → gray → blur → canny → save)
- [x] Re-run with one param changed executes only the affected suffix (asserted in `tests/test_engine.py` and `tests/test_benchmark.py`)
- [x] 1080p gray+blur+canny chain warm budget: **measured 2026-06-12: cold 25.5 ms, warm param change 6–7 ms** (budget < 150 ms in CI gate; interactive target is 100 ms)
- [x] 80 tests green (`pytest` ~0.7 s + 1080p benchmark)

**Phase 1 — MVP GUI: 🟡 IN PROGRESS — interactive core delivered.** The
`cvflow-app` GUI runs the full tune loop end-to-end (docs/05 Flow 1): open a
workflow → select a node → it opens in Viewer A → drag a param → the affected
suffix reruns in a background thread → the viewer, node LEDs, profiler and status
bar update. Built on **PySide6 alone** (bespoke `QGraphicsView` editor, docs/01
§7.3 — see deviations). Verified headless (offscreen) in `tests/test_app_smoke.py`.
Remaining Phase-1 scope (nodes toward ~35, Video scrub, custom-script node, GL
viewer, dependency highlight, structural undo, CI-qt) is listed under Next steps.

## What exists (implemented + tested)

| Area | State |
|---|---|
| Core model | `Graph` (cycle + type checks at connect, replace-on-reconnect, listeners), `NodeInstance`, declarative `Node`/`@node`, ports, params (Int/Float/Bool/Enum/String/Path + Range/Point/Rect/Color/Code), `NodeRegistry` |
| Type system | `ImageBuffer` (frozen arrays, BGR-canonical, str or enum spaces), `ColorSpace`, `ContourSet`, port-type checks with auto-coercions (GRAY→BGR replicate, BINARY→GRAY) and reject-with-hint (BGR→GRAY → 'insert "To Gray"') |
| Engine | `ExecutionService.run()` (blocking), demand closure from observed/armed nodes, BLAKE2b Merkle fingerprints (params + node version + input fps + `external_state` like file mtime), byte-budgeted LRU `OutputCache` with pinning, worker-pool parallel dispatch (workers=0 → inline/deterministic), error isolation (ERROR → descendants BLOCKED, siblings run), side-effect arming, `RunReport`/`NodeMetrics`/EMA |
| Nodes (20) | **io:** Load Image, Save Image · **color:** To Gray, In Range (→BINARY mask), CLAHE (L-in-LAB for colour) · **filters:** Gaussian Blur, Invert, Median Blur, Box Blur, Bilateral, Unsharp Mask · **edges:** Canny (typed GRAY input + validate low≤high), Sobel, Laplacian (both 8-bit or raw signed float) · **threshold:** Threshold (global/Otsu/adaptive) · **morphology:** Morphology (erode/dilate/open/close/…) · **geometry:** Resize (scale/absolute), Rotate / Flip (lossless) · **analysis:** Find Contours (→ ContourSet, min-area filter) · **draw:** Draw Contours |
| GUI (`cvflow/app/`) | PySide6 app: dark theme, dockable Palette/Inspector/Viewers/Console-Errors-Profiler; bespoke `QGraphicsView` node editor (drag-connect with live type-check + coercion badges, box-select, Tab quick-add, palette drag-drop, status LEDs); auto-inspector from ParamSpecs (slider/spin/check/combo/path) with 30 ms debounced live re-run; `ExecutionController` (threaded, superseding, run-locked structural edits); `ImageView` (zoom/pan/pixel-probe, channel isolation, range-aware normalize, contour overlay); param/label undo; save/load + autosave-of-UI-viewers. Entry: `cvflow-app` / `python -m cvflow.app`. See [README](cvflow/app/README.md) |
| SDK | `cvflow.sdk` facade (only legal import for nodes), `cvflow.sdk.testing` (`run_node`, synthetic images) |
| Persistence | workflow JSON schema v1 (atomic writes, stable ids, graph/ui separation, base_dir for relative assets), permissive load with issues list, strict on unknown types/newer schema |
| Plugins | builtin package scan + pip entry-point group `cvflow.nodes`, failure isolation (`PluginFailure`) |
| CLI | `cvflow run` (`--set node.param=value`, `--target`, `--no-sinks`, `--profile`, `--workers`), `validate`, `nodes list` |
| Examples | `examples/make_demo.py` (also the programmatic graph-building reference), `examples/workflows/edges_demo.cvflow.json` |

## Deliberate deviations from the design docs (so far)

These are *intentional*; if you change one, update the relevant doc.

1. **No separate dirty set** (docs/02 §2 mentions dirty ∩ demand): params/external
   state are inside the fingerprint, so "dirty" is subsumed by cache misses. Simpler
   and equally incremental. A dirty set returns only if fingerprint walks ever profile
   as hot (they're O(nodes) tiny hashes — unlikely).
2. **`cvflow/sdk/` is a package**, not the single `sdk.py` from docs/01 folder tree —
   needed for `cvflow.sdk.testing` (docs/04 §8 already used that path).
3. **Scheduler lives inside `engine/executor.py`** rather than a separate
   `scheduler.py` — one cohesive ~350-line module today; split when `streaming.py`
   lands in Phase 2.
4. **`NodeInstance.disabled` is persisted but ignored by the engine** — bypass
   semantics arrive with the GUI (Phase 1).
5. **Not yet created** (planned, see docs): `engine/streaming.py` (Phase 2),
   `cvflow/services/` (session/models — Phase 1/3), `io/migrations/` (first needed at
   schema v2), placeholder nodes for missing plugins (Phase 1), user plugins folder
   + hot reload (Phase 2). *(RangeParam/RectParam/PointParam/ColorParam/CodeParam
   were on this list; all five landed 2026-07-25 with their inspector widgets.
   The pick-in-viewer **gesture** for Rect/Point is still outstanding — that is
   viewer→inspector wiring, not a param-type gap.)*
6. **`ImageBuffer` accepts `"GRAY"` strings** as well as `ColorSpace.GRAY` —
   ergonomics addition discovered while writing the first nodes.
7. **Bespoke `QGraphicsView` node editor instead of NodeGraphQt** (docs/01 §7.3
   updated inline; docs/08 Phase 1 noted). Driver: no verified Python-3.14 support
   for NodeGraphQt/superqt/qtawesome; PySide6 6.11 ships an abi3 wheel that works.
   R3 (docs/09) realized early, resolved via the planned `GraphViewPort` seam. GUI
   deps trimmed to **PySide6 only** (`pyproject` `app` extra updated).
8. **Undo covers params + labels only** (coalesced one-step-per-gesture, docs/05
   §5). Structural undo (add/remove/connect) is a Phase-1 gap — the `QUndoStack`
   is in place, structural `QUndoCommand`s aren't written yet.
9. **Viewer uses CPU QImages, not GL textures** (docs/05 §2.4 wanted GL). The
   `ImageView` interface is GL-ready; the texture-upload path is deferred to
   Phase 2. Fine at still-image MVP scale.
10. **`NodeInstance.disabled`** is still persisted-but-ignored (was deviation #4);
    the GUI does not yet expose node bypass (`D`). Unchanged this session.

## Next steps (in order)

> **Under git since 2026-07-25** (session 4): branch `main`, initial commit
> `b9092ed` = the whole tree at 80 tests green. `.gitignore` excludes `.venv/`,
> `__pycache__`, `.pytest_cache`, `*.egg-info`, `.claude/settings.local.json` and
> the `examples/out/` sink output; `examples/assets/sample.png` **is** tracked so
> a fresh clone can run the demo. `.gitattributes` pins `eol=lf` so a Windows
> checkout doesn't rewrite every file. No remote yet — that gates CI (step 7).
>
> **CODE_REVIEW is fully closed** (2026-07-25, same session): §1.1 params
> snapshot, §1.2 armed-run publication + re-arm on supersession, §1.3 numeric
> profiler sort, §2.4 stable category colours, §2.5 middle-button pan without
> synthetic `QMouseEvent`s, §2.6 log handler removed on close, §2.7 unknown-spec
> widget fallback, §2.8 `Resize` keeps BINARY masks binary, §2.9 param-to-pixel
> latency now measured. **97 tests** green (was 80). Every new regression test
> was run against the pre-fix code and confirmed failing. §2.5 is the one fix
> without a test — it is a mouse-gesture path, and synthesizing the drag is what
> the fix exists to avoid (related gap: §2.11 below). §2.2, §2.3 fold into step
> 2 (editor/viewer depth); §2.1, §2.10, §2.11 are under "Known weak spots".
>
> **⚑ Param-to-pixel is now MEASURED, not estimated** (§2.9). `cvflow/app/
> latency.py` times the real interval — inspector edit → viewer pixmap, both
> ends on the GUI thread, so the 30 ms debounce, queued-signal delivery and any
> GUI backlog are all inside the number. Engine timings alone undercount.
> **1080p load→gray→blur→canny, offscreen, 40 edits: p50 38 ms, p95 48 ms,
> max 53 ms** against the docs/08 budget of 100 ms — *passing with roughly 2×
> headroom, and ~30 ms of it is the debounce.* p95 shows live in the status bar;
> `test_param_to_pixel_latency_gate` guards it at a loose 300 ms (gross
> regressions only, no CI flake). Caveat: offscreen, so it excludes real
> compositing/vsync — the CPU path is identical, but re-measure on a real
> display before declaring the exit criterion met.
>
> **Node packs: 11 → 22** (session 4). **152 tests** green. While writing batch
> 1, `GaussianBlur` turned out to carry the identical BINARY-label bug
> CODE_REVIEW §2.8 found in `Resize` — fixed, and `docs/04 §1` updated with it
> since that node *is* the reference example every plugin author copies.
>
> **The five missing `ParamSpec` types landed** (was deviation #5): `RangeParam`,
> `PointParam`, `RectParam`, `ColorParam`, `CodeParam`, each with an inspector
> widget, CLI `parse()` support and a JSON round-trip that restores the *tuple*
> — a list would re-fingerprint every node on reload and re-execute whole graphs.
> `ColorParam` stores BGR so nodes hand it straight to cv2; the RGB swap lives in
> the widget alone. Crop ROI and Filter Contours were written on top of them the
> same session, which is what proved the types usable rather than merely present.

1. **Keep broadening node packs toward ~35** — **22 done**, and the five
   `ParamSpec` types that gated a third of the remainder now exist. Split by
   what each group still needs (detail in [nodes/README](cvflow/nodes/README.md)):
   - **No blockers, pure SDK work:** split/merge channels, warp affine,
     perspective, overlay mask, blend, draw boxes, draw text, `util/`
     switch/math/display-text. Start here.
   - **Decide new data types first** — line segments, circles, a detections
     table. These gate connected components, Hough lines/circles, template
     match, bounding boxes, statistics. `types/geometry.py` says the catalog
     "arrives with the nodes that produce them"; this is that moment, and the
     decision is worth making deliberately rather than one node at a time.
   - **GUI work, not node work:** pick-in-viewer for `RectParam`/`PointParam`
     (a viewer→inspector gesture — Crop ROI already works, typed numerically);
     the custom Script node needs `cacheable = False` and a declared-ports UI.
2. **Editor + viewer depth** (docs/05 §2.2, §2.4): dependency highlight on
   selection, node bypass (`D`), backdrops/reroutes, heat overlay,
   thumbnails-on-node, **structural undo** (`QUndoCommand`s for
   add/remove/connect — deviation #8); GL texture path (deviation #9), 2×2
   layout + linked compare + wipe, histogram/false-colour LUT, Data-inspector
   tree panel. Folded in here: CODE_REVIEW §2.2 (confirm in the status bar that
   an armed run saved, and that a re-armed retry happened) and §2.3 (a viewer
   switched to a `ContourSet` node keeps the previous node's pixels while the
   header names the contours node — contours-over-source is genuinely useful,
   the mislabelling is the bug).
3. **Video File node in seekable-scrub mode** (frame slider) — the last Phase-1
   source type before live streaming (Phase 2).
4. **Persistence polish:** restore docks/viewers/pins from the workflow `ui`
   section on open (write path exists — `_collect_ui`); autosave + kill-9 recovery.
5. **CI** — GitHub Actions matrix (Windows + Linux), `pytest` (now includes the
   offscreen GUI smoke suite via `QT_QPA_PLATFORM=offscreen`) + the benchmark gate.
   Local git is done; this now only needs a GitHub remote + push.
6. Phase 1 exit per docs/08: rebuild three real past experiments faster than their
   script versions; **param-to-pixel p95 < 100 ms at 1080p — measured, 48 ms
   (see above); re-confirm on a real display**; save/reopen restores graph +
   viewers exactly.

## Known weak spots (honest list)

- `Graph.topo_order` is O(V·E) (rescans edge list); fine at prototype scale, index it
  if graphs grow past a few hundred nodes.
- Engine `run()` is synchronous; the GUI must wrap it in a worker thread (by design —
  docs/02 §8 — the debounced async controller is a Phase 1 client-side concern).
- `EnumParam` for Canny aperture stores strings ("3"/"5"/"7") — works, but an
  int-choices EnumParam variant would be cleaner.
- No logging configuration file yet; CLI uses basicConfig only.
- `ExecutionController.mutate()` blocks the GUI thread for as long as the
  in-flight *node* takes, because the engine polls cancellation only *between*
  nodes (CODE_REVIEW §2.1). Invisible today — every node is ms-scale — but it
  becomes a real freeze the day a slow node lands (template match, custom
  script, big morphology). Fix then: `ctx.is_cancelled()` checkpoints inside
  long-running nodes, and/or queue structural edits for the worker to apply
  between runs instead of blocking on them.
- **Per-node queued signals will storm the GUI thread at scale** (CODE_REVIEW
  §2.10): `EngineHooks → ExecutionController` emits `nodeStatus`/`outputsReady`
  once per node. Fine at 11 nodes; docs/05 §6 (N6) wants batched-per-report
  badge/metric updates by ~200. Don't fix prematurely — revisit when graphs grow.
- **Port drag-wiring has no automated coverage** (CODE_REVIEW §2.11):
  `PortItem.mousePressEvent → GraphScene.begin_wire/update_wire/finish_wire`.
  Offscreen can't synthesize drags well; the tractable version is a scene-level
  test calling `begin_wire`/`finish_wire` directly with scene positions over a
  target port, asserting an edge appears and that incompatible ports emit
  `connectionRejected`. Middle-button pan (§2.5) is untested for the same reason.
- **If `service.run()` raises, that run's armed set is lost** (the controller
  logs the exception and continues). Left deliberate while fixing §1.2: the
  re-arm path carries arms forward on *supersession*, where a retry is certain
  to be different, but auto-retrying after a crash could spin forever on a
  persistent bug. A sink that vanishes this way is silent — worth surfacing in
  the Errors panel when §2.2 (armed-run status feedback) is done.
