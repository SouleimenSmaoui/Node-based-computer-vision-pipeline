# cvflow.app — the PySide6 GUI (Phase 1)

The visual editor over the headless core. **This is the only package allowed to
import Qt** (hard rule 1, docs/01 §3); it drives the same public engine/graph/
registry surface the CLI uses — it never reaches around the API.

Run it:

```powershell
.venv\Scripts\cvflow-app.exe                       # empty workflow
.venv\Scripts\cvflow-app.exe examples\workflows\edges_demo.cvflow.json
.venv\Scripts\python.exe -m cvflow.app <workflow>  # equivalent
```

Install the GUI dependency (PySide6 only): `pip install -e .[app]`.

## Layout

| File / dir | What it is |
|---|---|
| `__init__.py` | `run_app()` — QApplication + MainWindow bootstrap |
| `__main__.py` | `python -m cvflow.app` / `cvflow-app` entry point |
| `theme.py` | dark QSS palette, Okabe-Ito category colours, wire/status colours |
| `imaging.py` | `ImageBuffer → QImage` (range-aware normalization, channel isolation) |
| `session.py` | `WorkflowSession` — graph + controller + path/dirty + undo stack |
| `controllers/execution_controller.py` | debounced, superseding, threaded client of `ExecutionService` |
| `viewer/image_view.py` | `ImageView` — zoom/pan/probe, channel/normalize, contour overlay |
| `inspector/` | auto-generated parameter editors from `ParamSpec`s |
| `graphview/` | bespoke `QGraphicsView` node editor (items/scene/view/palette) |
| `panels/` | console/log, errors, profiler table |
| `main_window.py` | docking, menus/toolbar, status bar, and all the signal wiring |

## The interactive loop (docs/02 §4, docs/05 Flow 1)

Selecting a node opens it in **Viewer A** and marks it *observed*. A parameter
edit in the **Inspector** →

```
ParamWidget.edited ─30ms debounce─▶ ExecutionController._launch
   ▶ background thread: ExecutionService.run(observed, token)
       ▶ engine hooks (worker thread) ─Qt queued signals─▶ GUI thread
           ▶ node LEDs / timings, Viewer image, profiler, status totals
```

Because params + external state live inside the fingerprint, only the affected
suffix re-executes; upstream is served from cache. A newer edit cancels the
in-flight run via a `CancellationToken` (latest-wins). The GUI thread never
blocks on the engine.

### Threading rules this loop depends on (CODE_REVIEW §1.1–§1.2, fixed 2026-07-25)

- **Param edits skip the run-lock, and that is safe only because the engine
  snapshots params once per node per run** (`engine/dispatch`). Two reads at
  different times let an edit land between fingerprinting and execution, caching
  a result under the wrong key — a wrong image served on every later visit to
  that value. Don't reintroduce a second read.
- **`_armed` is published under `_cond`, together with the launch.** Written
  outside it, the worker's read-and-clear could wipe the arm: the user clicks
  **Run**, nothing executes, nothing explains why.
- **A superseded armed run re-arms its unfinished sinks** (`_incomplete_sinks`).
  Otherwise a slider tick landing during a save silently swallows the export —
  the arm was already consumed and the report is discarded. `arm_and_run` unions
  rather than replaces so a later Run click can't drop a carried-forward arm.

## Deliberate design choices (deviations recorded in STATUS.md)

- **Bespoke editor, not NodeGraphQt.** docs/08 named NodeGraphQt for Phase 1 with
  a bespoke `QGraphicsView` editor as the Phase-3 fallback (docs/01 §7.3). With
  no verified Python-3.14 support for NodeGraphQt/superqt/qtawesome, we pulled the
  fallback forward. The GUI depends on **PySide6 alone**.
- **Undo covers params + labels** (coalesced one-step-per-gesture, docs/05 §5).
  Structural undo (add/remove/connect) is a known MVP gap.
- **CPU QImages, not GL textures.** The GL viewport + zero-copy upload is the
  Phase-2 viewer upgrade (docs/05 §2.4); the `ImageView` interface already fits it.

## Not yet (Phase 2+, docs/08)

Live webcam/RTSP, batch runner UI, proxy-resolution preview, multi-view > 2 +
wipe, data-inspector tree, custom-script editor dialog, layout persistence in the
workflow `ui` section, command palette (`Ctrl+K`), heat overlay.
