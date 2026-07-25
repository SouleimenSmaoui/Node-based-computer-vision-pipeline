# 05 — GUI Design

Design target: the keyboard-centric ergonomics of a compositing tool (Nuke/Blender) with
the inspectability of an IDE — built for an expert user (persona P1) on large monitors,
dark lab environments, and high-DPI industrial laptops. Every view is a `QDockWidget`:
the layout below is the default, not a cage.

---

## 1. Main window layout (default)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ File  Edit  Graph  Run  View  Plugins  Help            ▶ Run  ⏸  ● REC  ⚙    │
├───────────────┬──────────────────────────────────────────┬───────────────────┤
│ NODE PALETTE  │  GRAPH CANVAS (tab: inspect_pcb.cvflow)  │ INSPECTOR         │
│ [search… 🔍]  │                                          │ ┌───────────────┐ │
│ ▾ Input/Output│   ┌─────────┐    ┌──────────┐            │ │ Gaussian Blur │ │
│   Load Image  │   │Load Img │───▶│ To Gray  │──┐         │ │ n7 · 11.4 ms ✓│ │
│   Image Folder│   └─────────┘    └──────────┘  │         │ ├───────────────┤ │
│   Video File  │                                ▼         │ │ Kernel size   │ │
│   Webcam      │                  ┌─────────────────┐     │ │ ▮▮▮▮▮▯▯ [ 9]  │ │
│ ▾ Filtering   │                  │ Gaussian Blur ✓ │     │ │ Sigma         │ │
│   Gaussian ◀──│── drag           │ 11.4ms  [thumb] │     │ │ ▮▮▯▯▯▯▯ [2.0] │ │
│   Median      │                  └─────────────────┘     │ │ □ expose as   │ │
│   Bilateral   │                          │               │ │   input       │ │
│ ▾ Edges       │                          ▼               │ ├───────────────┤ │
│   Canny       │                  ┌──────────────┐        │ │ ⓘ node help   │ │
│   Sobel       │                  │ Canny    ⚠ ✗ │        │ └───────────────┘ │
│ ▾ Morphology…│                   └──────────────┘        │                   │
├───────────────┴──────────────────────────────────────────┴───────────────────┤
│ VIEWER A (n7·out) ⌖ 100% PROXY │ VIEWER B (n9·out) 🔗linked │ DATA INSPECTOR  │
│  [image w/ contour overlay]    │  [edge map]                │ n9 contours: 17 │
│  px(412,221)=BGR(34,77,210)    │                            │ ▸ area μ=412px² │
├──────────────────────────────────────────────────────────────────────────────┤
│ CONSOLE / ERRORS / PROFILER                    pipeline 38 ms · cache 5/8 · ✓ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 2. Panel specifications

### 2.1 Node palette (left)

Search-first (fuzzy over label, id, keywords, category), collapsible categories, drag to
canvas **or** double-click to insert at last cursor position. The same model powers the
**Tab quick-add menu**: press `Tab` over the canvas → floating search → Enter inserts the
node *and auto-wires* its first compatible input to the currently selected node's output
(the single biggest speed win borrowed from Nuke/Blender).

### 2.2 Graph canvas (center)

- One tab per open workflow. Pan (Space-drag / MMB), zoom-to-cursor (wheel), `F` fit
  selection, `Ctrl+A` select all, box-select; reroute dots; backdrop groups with labels.
- **Wires** are bezier, colored by data type (image = white, mask = cyan, geometry =
  orange, detections = magenta, scalar = gray); coercion badge dot (docs/03 §6); invalid
  connection preview is red with the reason in the status bar.
- **Node visuals**: header tinted by category; status LED — gray idle, blue pulsing
  running, green ok, amber validation warning, red error, ⟲ stateful badge, 💾
  side-effect badge; last execution time as a small right-aligned label; optional 96 px
  **thumbnail** of the primary image output on the node body (off by default above 50
  nodes; thumbnails are produced from the already-computed output at preview time, never
  by extra executions).
- **Heat overlay** toggle (`View ▸ Profile heat`): node tint ∝ share of last run's time —
  the "where is my pipeline slow" answer at a glance (reads RunReport, docs/02 §9).
- **Dependency highlight**: selecting a node dims everything outside its
  ancestors/descendants (the literal demand/dirty closures — debugging requirement F9).
- Right-click context: open in Viewer A/B, pin preview, disable node (pass-through where
  type-legal — implemented as engine-level bypass, great for A/B testing a filter's
  contribution), insert suggested converter, copy as plugin snippet.

### 2.3 Inspector (right)

Auto-generated from `ParamSpec`s (docs/04 §1.1): sliders+spinbox pairs, dropdowns,
checkboxes, range sliders, path pickers, color swatches, point/rect pickers that arm
viewer pick-mode. Header shows node label (editable), id, status, last timing. Live edits
follow the debounced-run pipeline (docs/02 §4); slider press/release brackets one undo
macro. Multi-select shows shared parameters (batch edit). `visible_if` rules show/hide
dependent params dynamically.

> **Build note (2026-07-25).** All five tuple/colour/code editors exist and are
> generated automatically; dispatch is by spec *type*, never by `widget_hint` (a
> hint-keyed table sent a non-`IntParam` to the int editor and crashed it —
> CODE_REVIEW §2.7). Two deviations from the description above, both deliberate:
>
> - **Range/point/rect are labelled spin-box groups, not a two-handle slider or an
>   armed viewer picker.** Qt ships no two-handle slider, and the GUI is PySide6-only
>   (STATUS.md deviation #7), so a range slider means writing one. **Pick-in-viewer
>   is a viewer→inspector gesture, not a param-type feature** — Crop ROI and
>   Perspective Warp are fully usable typed numerically, so this is UX polish rather
>   than a blocker (Flow 4 above is still the target).
> - **`ColorParam` values are BGR**, matching OpenCV so nodes pass them straight to
>   `cv2.rectangle`. Qt is RGB; that swap lives in the swatch widget alone.
>
> Not yet built: multi-select batch edit, `visible_if`, and the undo macro bracketing
> a slider gesture (undo currently coalesces per gesture but is not a formal macro).

### 2.4 Viewers (the product's soul)

`QGraphicsView`-based canvas with an OpenGL viewport; the displayed `ImageBuffer` is
uploaded as a GL texture (numpy→QImage zero-copy where stride permits, mipmapped for
smooth zoom-out of 20 MP frames).

- **Navigation:** wheel zoom-to-cursor (10%–6400%), pan drag, `F` fit, `1` = 100%,
  double-click fit. Zoom/pan state persists per viewer per node.
- **Pixel probe:** hover readout `x,y → BGR(…)/GRAY(…)/float(…)` + zoom-window loupe on
  `Ctrl` (essential for threshold tuning).
- **Channel/display controls:** R/G/B/A/gray isolation, float normalization mode
  (`range`-aware, docs/03 §3), false-color LUT for float/heat data, gamma toggle,
  histogram popover, export-frame button.
- **Overlay layers:** any geometric output (same node or *another* node — drag a
  geometry output onto a viewer) renders as vector `QGraphicsItem`s above the image:
  contours, boxes+labels+confidence, keypoints/skeletons, masks as tinted half-alpha
  fills, measurements as ruled annotations. Per-layer visibility/color/width controls.
  Vector overlays stay crisp at any zoom and cost nothing on re-zoom (no image re-render)
  — this is why overlays are *not* baked into pixels anywhere in the GUI path.
- **Multi-view compare:** layouts 1×1, 2×1, 1×2, 2×2; 🔗 link toggle synchronizes
  zoom/pan/probe across panes (pixel-accurate A/B of two pipeline stages); optional wipe
  slider in 1×1 comparing two pinned sources (Phase 2).
- **PROXY badge** when showing proxy-resolution results (docs/02 §4.1); REC badge during
  recording.

### 2.5 Console / Errors / Profiler (bottom, tabbed)

- **Console:** structured log stream (node-scoped, filterable by level/node).
- **Errors:** one card per `NodeError` — message, node link (click → select + center the
  node), expandable traceback; amber cards for validation issues.
- **Profiler:** sortable table per node — last ms, EMA ms, % of pipeline, cache
  hit-rate, output bytes; totals row; stream mode adds source FPS vs processed FPS and
  drop counter (docs/02 §7). One click jumps from the slowest row to the node.

### 2.6 Data inspector

Tree view of any selected output (the `to_tree` contract, docs/03 §7): arrays show
shape/dtype/min/max/mean/histogram-sparkline; lists/dicts drill down; contours/detections
enumerate with per-item metrics; values copyable as JSON. Pin to keep watching one output
while selecting other nodes.

## 3. Key interaction flows

**Flow 1 — build & tune (the core loop).** Drag Load Image → pick file (viewer shows it
immediately because dropping a source auto-opens Viewer A on its output) → `Tab` "gray"
→ Enter (auto-wired) → `Tab` "canny" → Enter → drag Canny thresholds: RangeParam slider →
30 ms debounce → engine runs `canny` only (upstream cached) → Viewer A updates in ~15 ms →
status bar `pipeline 4.1 ms · cache 2/3`. No run button involved (the run button exists
for armed/side-effect execution).

**Flow 2 — compare two denoisers.** Wire Gaussian and Bilateral in parallel from the same
source; right-click → Viewer A / Viewer B; link 🔗; zoom both at 400 % over an edge;
tune each side's params; the loser gets node-disable to confirm contribution downstream.

**Flow 3 — error recovery.** Canny fed a BGR image via an `Any`-output script node:
runtime check fails → red badge, Errors card "expected GRAY, got BGR — insert To Gray",
click card → node centered → right-click → "Insert To Gray" → re-run is automatic.

**Flow 4 — ROI by direct manipulation.** Crop ROI selected → inspector RectParam → "pick
in viewer" → viewer arms rubber-band → drag rectangle → params fill in, pipeline reruns
live while dragging (proxy mode), exact values fine-tunable in spinboxes afterwards.

**Flow 5 — live stream tuning.** Webcam node → Start stream (toolbar ▶ becomes stream
controls) → FPS/drop counters in status bar → sliders retune between frames atomically
(docs/02 §7.1) → ● REC arms Save Video sink with lossless queueing.

**Flow 6 — batch.** Image Folder source → Run Batch dialog: target sinks checklist,
on-error policy, progress with per-file errors → results table + CSV written; the same
dialog generates the equivalent `cvflow run` CLI command for automation (deliberate
GUI→CLI bridge).

## 4. Keyboard map (excerpt)

`Tab` quick-add · `Del` delete · `Ctrl+C/V/D` copy/paste/duplicate (paste offsets, keeps
internal wires) · `Ctrl+Z/Y` undo/redo · `D` disable node · `F` fit · `1` 100 % ·
`P` pin preview · `Ctrl+Enter` arm+run sinks · `Space` (hold) pan · `Ctrl+K` command
palette (every action searchable — discoverability for the long tail without menu
spelunking).

## 5. Undo model

Single `QUndoStack` per workflow document covering **graph edits and parameter changes**
(add/remove/connect/move/group/param). Continuous gestures (slider drags, node drags)
coalesce via macro begin/end on press/release — one undo step per gesture, matching user
intent. Viewer state (zoom/pan) is deliberately *not* undoable (navigation isn't
editing). Engine state never participates: undo manipulates the document; dirty
propagation + caching make re-execution after undo automatically minimal — a free but
important synergy of the fingerprint design.

## 6. Visual design & platform details

- **Dark theme default** (QSS, near-Nuke palette: #2b2b2b surfaces, #3c3f41 panels,
  accent #4a9eff); light theme Phase 2. Image viewers always neutral-gray surround
  (#202020) — never pure black/white, which biases perceived contrast during tuning.
- Category colors are colorblind-safe (Okabe-Ito palette); status additionally encoded by
  icon shape, never color alone.
- Full high-DPI support (`Qt::AA_EnableHighDpiScaling`, SVG icons only).
- Window layout (docks, open viewers, pinned nodes) persists per workflow in the
  workflow file's `ui` section (docs/06) — reopening a project restores the working
  context, which is half the "resume experiment quickly" value.
- GUI perf budgets: canvas interactions ≥ 60 fps to 200 nodes (NodeGraphQt validated
  range; LOD: hide thumbnails/labels when zoomed out); viewer pan/zoom ≥ 60 fps at 20 MP
  (GL textures make this trivial after upload); badge/metric updates batched per run
  report, not per node completion, to avoid GUI-thread storms (N6).
