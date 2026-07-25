# CVFlow — Visual Computer Vision Workflow Builder

> **Working title:** CVFlow. A professional desktop application for building, tuning, and
> running computer-vision pipelines as visual node graphs — no per-experiment scripting.

**Status:** Phase 0 (headless foundations) complete, and **Phase 1 GUI interactive
core delivered** — core model, DAG engine with fingerprint caching, 11 nodes, JSON
persistence, CLI, and a PySide6 desktop app that runs the live tune loop end to end.
80 tests green. See [STATUS.md](STATUS.md) for the precise state and next steps, and
[CLAUDE.md](CLAUDE.md) for the contributor/AI-session guide.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[app,dev]"  # app = PySide6 GUI
.venv\Scripts\python.exe -m pytest                       # 80 tests, ~1 s
.venv\Scripts\python.exe examples\make_demo.py           # generate demo workflow

# GUI: open the demo, then drag a slider and watch only the affected suffix rerun
.venv\Scripts\cvflow-app.exe examples\workflows\edges_demo.cvflow.json

# Headless (same engine, same workflow file)
.venv\Scripts\cvflow.exe run examples\workflows\edges_demo.cvflow.json --profile
.venv\Scripts\cvflow.exe run examples\workflows\edges_demo.cvflow.json --set blur.kernel=9 --set canny.low=80
```

Measured on the dev machine (2026-06-12): cold 5-node 1080p run 25 ms; warm
param change re-executes only the affected suffix in ~6 ms.

---

## The problem

A CV engineer testing a new image-processing idea today writes a throwaway Python script:
load image → tweak `cv2.GaussianBlur(img, (5,5), 1.2)` → rerun → squint at `cv2.imshow` →
edit → rerun. Every experiment pays the same tax: boilerplate I/O, manual parameter editing,
no caching, no comparison of intermediate results, nothing reusable.

## The product

CVFlow is a node-graph editor (in the spirit of HALCON HDevelop, LabVIEW, Nuke, and
Node-RED) where a pipeline is a graph of typed blocks:

```
[Load Image] → [To Gray] → [Gaussian Blur] → [Canny] → [Find Contours] → [Draw Contours] → [Viewer]
                                  ▲
                       kernel/sigma sliders — live retune,
                       only downstream nodes re-execute
```

Core promises:

1. **Param-to-pixel latency under ~100 ms** for typical pipelines on 1080p images —
   tuning a slider feels like adjusting a physical knob, not re-running a script.
2. **Incremental execution** — changing one parameter re-runs only the affected
   downstream nodes; everything upstream is served from cache.
3. **Inspect anything** — every node's output can be opened in a viewer, compared
   side-by-side, probed per-pixel, and overlaid with geometry.
4. **Extensible without forking** — new nodes are plain Python classes discovered from a
   plugins folder or pip packages; built-in nodes use the exact same API.
5. **Headless core** — the same workflow JSON runs from the GUI, a CLI, or (later) a
   server, because the engine has zero GUI dependencies.

## Technology stack (summary)

| Layer | Choice | License | Why (full rationale in docs) |
|---|---|---|---|
| Language | Python 3.11+ | PSF | CV ecosystem lives here; target users are Python CV engineers |
| Image processing | OpenCV + NumPy | Apache-2.0 / BSD | Industry standard; releases the GIL during heavy ops |
| GUI | PySide6 (Qt 6) | LGPL-3 | Native performance for big images, dockable pro UI, commercial-friendly license |
| Node editor | Bespoke `QGraphicsView` editor behind an adapter | ours | Python-3.14 compat: NodeGraphQt has no verified 3.14 support (docs/01 §7.3); the `GraphViewPort` seam kept it swappable |
| Engine | Custom DAG engine (~2k LOC) | ours | Millisecond-scale incremental re-eval; orchestrators like Dask/Prefect are the wrong tool |
| Inference (future) | ONNX Runtime | MIT | One runtime, many model sources, CPU/GPU execution providers |
| Persistence | JSON workflow files (+ optional SQLite run history) | — | Diffable, hand-editable, VCS-friendly |

## Document map

| Doc | Contents |
|---|---|
| [docs/01-architecture.md](docs/01-architecture.md) | Requirements, architectural principles, layers, module breakdown, folder structure, data-flow architecture, technology decisions & alternatives considered |
| [docs/02-execution-engine.md](docs/02-execution-engine.md) | DAG model, pull-based incremental evaluation, fingerprint caching, threading, cancellation, debouncing, streaming mode, error semantics, profiling |
| [docs/03-type-system.md](docs/03-type-system.md) | Port/data types, `ImageBuffer`, color-space policy, geometry & detection types, tensors, connection rules and coercions |
| [docs/04-node-plugin-api.md](docs/04-node-plugin-api.md) | Declarative node API, lifecycle, execution context, plugin discovery/packaging/versioning, custom script node, node testing harness |
| [docs/05-gui-design.md](docs/05-gui-design.md) | Window layout & mockups, graph editor UX, inspector, viewers & overlays, parameter widgets, debugging UI, keyboard model, undo |
| [docs/06-persistence.md](docs/06-persistence.md) | Workflow JSON schema with example, migrations, asset handling, project bundles, settings, run-history database |
| [docs/07-class-diagrams.md](docs/07-class-diagrams.md) | Class diagrams (core, engine, plugin, GUI) and the parameter-change sequence diagram |
| [docs/08-roadmap.md](docs/08-roadmap.md) | Phase plan with exit criteria, MVP definition (scope + node list), industrial-grade definition, estimates |
| [docs/09-risks.md](docs/09-risks.md) | Risk register with likelihood/impact/mitigations |
| [docs/10-libraries.md](docs/10-libraries.md) | Recommended libraries with licenses, alternatives, and license warnings (PyQt, Ultralytics AGPL, …) |
| [docs/11-ai-integration.md](docs/11-ai-integration.md) | Scalability plan for YOLO/SAM/OCR/pose/tracking nodes without architectural change |

## Reading order

For a first pass: `01-architecture` → `02-execution-engine` → `04-node-plugin-api` →
`05-gui-design` → `08-roadmap`. The rest are reference documents.
