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
| Core model | `Graph` (cycle + type checks at connect, replace-on-reconnect, listeners), `NodeInstance`, declarative `Node`/`@node`, ports, params (Int/Float/Bool/Enum/String/Path), `NodeRegistry` |
| Type system | `ImageBuffer` (frozen arrays, BGR-canonical, str or enum spaces), `ColorSpace`, `ContourSet`, port-type checks with auto-coercions (GRAY→BGR replicate, BINARY→GRAY) and reject-with-hint (BGR→GRAY → 'insert "To Gray"') |
| Engine | `ExecutionService.run()` (blocking), demand closure from observed/armed nodes, BLAKE2b Merkle fingerprints (params + node version + input fps + `external_state` like file mtime), byte-budgeted LRU `OutputCache` with pinning, worker-pool parallel dispatch (workers=0 → inline/deterministic), error isolation (ERROR → descendants BLOCKED, siblings run), side-effect arming, `RunReport`/`NodeMetrics`/EMA |
| Nodes (11) | **io:** Load Image, Save Image · **color:** To Gray · **filters:** Gaussian Blur, Invert · **edges:** Canny (typed GRAY input + validate low≤high) · **threshold:** Threshold (global/Otsu/adaptive) · **morphology:** Morphology (erode/dilate/open/close/…) · **geometry:** Resize (scale/absolute) · **analysis:** Find Contours (→ ContourSet, min-area filter) · **draw:** Draw Contours |
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
   schema v2), placeholder nodes for missing plugins (Phase 1), RangeParam/RectParam/
   PointParam/ColorParam/CodeParam (Phase 1, with the inspector), user plugins folder
   + hot reload (Phase 2).
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
> **CODE_REVIEW §1 and §2.4–2.8 are fixed** (2026-07-25, same session): §1.1
> params snapshot, §1.2 armed-run publication + re-arm on supersession, §1.3
> numeric profiler sort, §2.4 stable category colours, §2.5 middle-button pan
> without synthetic `QMouseEvent`s, §2.6 log handler removed on close, §2.7
> unknown-spec widget fallback, §2.8 `Resize` keeps BINARY masks binary.
> **91 tests** green (was 80). Every new test was run against the pre-fix code
> and confirmed failing, so they are real regression guards. §2.5 is the one
> fix without a test — it is a mouse-gesture path, and synthesizing the drag is
> what the fix exists to avoid (related gap: §2.11 below).
>
> **Remaining CODE_REVIEW §2, triaged:** §2.9 is step 1 below; §2.2 (armed-run
> status feedback) and §2.3 (viewer mislabels a stale image under a contours
> overlay — contours-over-source is useful, the header claiming the contours
> node is the bug) fold into step 3, editor/viewer depth; §2.1, §2.10, §2.11 are
> under "Known weak spots"; §2.12 was already these Next steps.

1. **Measure param-to-pixel latency** (CODE_REVIEW §2.9) — docs/08 makes
   *measured p95 < 100 ms at 1080p* a Phase-1 exit criterion, and it has never
   been measured, only estimated. Timestamp in `InspectorPanel.paramEdited`,
   carry an edit-id through `ExecutionController`, log the delta when the viewer
   sets its pixmap, surface p95 in the status bar. Cheap, always-on, and worth
   having in place *before* the node count grows and a slow node appears.
2. **Broaden node packs toward the MVP ~35** (docs/08 Phase 1) — 11 done; still
   want: in-range colour mask, crop-ROI (with pick-in-viewer RectParam), rotate/
   flip/warp/perspective, median/bilateral/box/unsharp, Sobel/Laplacian, filter-
   contours + bounding boxes + connected components + Hough + template match,
   statistics, draw boxes/text/mask-blend, switch/math util, **custom Script node**
   (editor dialog). Pure SDK work; each needs a `tests/test_nodes.py` test.
3. **Editor depth** (docs/05 §2.2): dependency highlight on selection, node bypass
   (`D`), backdrops/reroutes, heat overlay, thumbnails-on-node, **structural undo**
   (`QUndoCommand`s for add/remove/connect — deviation #8).
4. **Viewer depth** (docs/05 §2.4): GL texture path (deviation #9), 2×2 layout +
   linked compare + wipe, histogram/false-colour LUT, Data-inspector tree panel.
5. **Video File node in seekable-scrub mode** (frame slider) — the last Phase-1
   source type before live streaming (Phase 2).
6. **Persistence polish:** restore docks/viewers/pins from the workflow `ui`
   section on open (write path exists — `_collect_ui`); autosave + kill-9 recovery.
7. **CI** — GitHub Actions matrix (Windows + Linux), `pytest` (now includes the
   offscreen GUI smoke suite via `QT_QPA_PLATFORM=offscreen`) + the benchmark gate.
   Local git is done; this now only needs a GitHub remote + push.
8. Phase 1 exit per docs/08: rebuild three real past experiments faster than their
   script versions; param-to-pixel p95 < 100 ms at 1080p; save/reopen restores
   graph + viewers exactly.

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
