# 10 — Recommended Open-Source Libraries

Selection principles: boring and maintained beats clever and fresh; licenses must be
compatible with internal *and* potential commercial distribution (LGPL acceptable as
dynamically-linked dependency, GPL not, AGPL never for runtime deps); core stays light —
heavy deps live behind extras (`cvflow[app]`, `[ml]`, `[camera]`).

## Core runtime

| Library | License | Role | Why this one / alternatives rejected |
|---|---|---|---|
| **Python 3.11+** | PSF | language | 3.11 perf gains matter for engine overhead; 3.12+ fine. Floor set by PySide6 support matrix |
| **numpy** | BSD | array substrate | non-negotiable ecosystem currency |
| **opencv-python** | Apache-2.0 | classic CV | the requirement itself. Note: wheels are CPU-only (docs/01 §7.8); `opencv-contrib-python` only if contrib nodes ship (SIFT is in main since patent expiry; SURF remains nonfree — excluded) |
| **blake3** or stdlib `hashlib.blake2b` | CC0/Apache / PSF | fingerprints | blake2b in stdlib = zero dep; blake3 optional speedup, not required |
| **msgpack** | Apache-2.0 | canonical param encoding for fingerprints | stable, fast, bytes-deterministic |
| **jsonschema** | MIT | workflow file validation | the reference implementation; pydantic rejected for core (heavier, and we need *schema-for-a-file*, not settings models) |
| **platformdirs** | MIT | config/cache/log paths | the standard successor to appdirs |
| **tomli/tomllib + tomli-w** | MIT/PSF | `cvflow.toml` | stdlib reader on 3.11+ |
| **rich** | MIT | CLI output, tracebacks | best-in-class terminal UX for `cvflow run/validate` |

## GUI (`cvflow[app]`)

| Library | License | Role | Notes |
|---|---|---|---|
| **PySide6** | LGPL-3 | Qt 6 binding | vs PyQt6 (GPL/commercial): same API, safe license. Decision detail docs/01 §7.2 |
| **NodeGraphQt** | MIT | node canvas | behind `GraphViewPort` adapter (risk R3). Alternatives: qtpynodeeditor (stale), pyqtgraph.flowchart (too basic), bespoke (Phase 3 option) |
| **superqt** | BSD-3 | labeled sliders, range sliders, large-int spinboxes | exactly the missing Qt widgets for parameter tuning; from the napari org, well maintained |
| **qtawesome** | MIT | icon font set | consistent icons without an asset pipeline |
| **pyqtgraph** | MIT | histogram popover, plots in profiler/inspector | proven fast Qt plotting; NOT used for the node canvas |

## Video & cameras (`cvflow[camera]`, Phases 2–3)

| Library | License | Role | Notes |
|---|---|---|---|
| **PyAV** | BSD | video files & RTSP demux/decode | ffmpeg bindings; vastly more robust than `cv2.VideoCapture` for RTSP/codec corner cases; cv2 capture remains the zero-dep webcam/file default |
| **imageio + imageio-ffmpeg** | BSD | fallback video writing | simple, reliable encode path for Save Video |
| **harvesters** | Apache-2.0 | GenICam/GenTL industrial cameras | the vendor-neutral standard route (needs a GenTL producer from the camera vendor) |
| **pypylon** | BSD-ish (Basler) | Basler cameras (reference vendor plugin) | most common industrial brand on benches; ships as a *plugin*, never core |

## ML & AI (`cvflow[ml]`, Phase 3 — full plan in docs/11)

| Library | License | Role | Notes |
|---|---|---|---|
| **onnxruntime / onnxruntime-gpu** | MIT | the inference runtime | one API, CPU/CUDA/DirectML/TensorRT execution providers; the keystone of the AI strategy |
| **rapidocr-onnxruntime** | Apache-2.0 | OCR node | pip-only, no system Tesseract binary to package; pytesseract kept as an alternative node (Apache, but requires bundling the Tesseract exe) |
| **supervision** | MIT | detection post-processing/annotation utilities | our `Detections` type mirrors it; either depend on it or stay convention-compatible — convention-compatible chosen for core, dep allowed in ml extra |
| ⚠️ **ultralytics (YOLOv8/11)** | **AGPL-3.0** | — | **do not ship as a dependency**: AGPL contaminates distribution. Strategy: load YOLO ONNX exports via onnxruntime, or Apache-licensed alternatives (YOLOX, RT-DETR, RF-DETR). Users may install ultralytics privately into their own plugin — their license call, not ours |
| **SAM / SAM2 (Meta)** | Apache-2.0 | segmentation nodes | weights via ModelManager; MobileSAM/ONNX exports for CPU-viable interactive use |
| **CuPy** (optional) | MIT | GPU array math for an accelerated node pack | only where profiling justifies it |

## Development & QA

| Library | License | Role |
|---|---|---|
| **pytest, pytest-qt, pytest-benchmark, hypothesis** | MIT | unit/GUI/perf/property tests (R14 edit-sequence fuzzing) |
| **ruff + mypy** | MIT | lint/format/types; import-rule enforcement (docs/01 §3) via ruff `tid` custom bans |
| **import-linter** | BSD | layer contract enforcement in CI |
| **PyInstaller** | GPL *with bootloader exception* (output unencumbered) | binaries/installers; alternative: Briefcase if PyInstaller fights Qt plugins |
| **Inno Setup** | free | Windows installer wrapper |
| **mkdocs-material** | MIT | docs site; node reference auto-generated from NodeSpec metadata |

## Explicitly rejected

- **Dask/Prefect/Airflow/RxPY** for execution — wrong granularity/semantics (docs/01 §7.4).
- **pydantic in core** — great library, wrong layer; descriptors already define params, and core must stay feather-light.
- **Electron/web UI** — latency & camera access (docs/01 §7.1).
- **SQLite for workflows** — documents must diff (docs/06 §1); SQLite only for run history.
- **PyQt6** — GPL/commercial licensing trap for a tool that will circulate inside companies.
