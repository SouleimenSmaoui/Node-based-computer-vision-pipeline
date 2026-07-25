# CLAUDE.md — project guide for Claude Code

CVFlow: a visual computer-vision workflow builder (node graphs over OpenCV).
Headless core + DAG engine exist and are tested; the Qt GUI is the next phase.

**Start every session by reading [STATUS.md](STATUS.md)** — it says exactly what is
implemented, what was deliberately deferred, and what the next step is.
The design documents in `docs/` (01–11) are the source of truth for *why* things are
built this way; don't re-litigate decisions recorded there without flagging it.

## Commands (Windows; venv lives in `.venv/`)

```powershell
.venv\Scripts\python.exe -m pytest                # full test suite (must stay green)
.venv\Scripts\cvflow.exe nodes list               # registered node types
.venv\Scripts\cvflow.exe run examples\workflows\edges_demo.cvflow.json --profile
.venv\Scripts\cvflow.exe run <wf> --set blur.kernel=9 --target canny --no-sinks
.venv\Scripts\cvflow-app.exe examples\workflows\edges_demo.cvflow.json  # launch the GUI
.venv\Scripts\python.exe examples\make_demo.py    # regenerate demo asset + workflow
.venv\Scripts\python.exe -m pip install -e .[app] # app extra = PySide6 (Qt GUI)
```

GUI tests run headless: `pytest` includes `tests/test_app_smoke.py`, which sets
`QT_QPA_PLATFORM=offscreen` and skips if PySide6 is absent. No display needed.

## Repository map

| Path | What it is | Details |
|---|---|---|
| `docs/01…11-*.md` | full architecture & design docs (written before code) | read 01, 02, 04 first |
| `cvflow/core/` | graph model, type system, params/ports/node specs | [README](cvflow/core/README.md) |
| `cvflow/engine/` | fingerprint cache, scheduler/executor, run reports | [README](cvflow/engine/README.md) |
| `cvflow/sdk/` | **the only import surface for nodes** + testing harness | [README](cvflow/sdk/README.md) |
| `cvflow/nodes/` | built-in node packs (20 nodes, MVP target ~35) | [README](cvflow/nodes/README.md) |
| `cvflow/io/` | workflow JSON v1, asset path resolution | [README](cvflow/io/README.md) |
| `cvflow/plugins/` | node discovery (builtin scan + pip entry points) | [README](cvflow/plugins/README.md) |
| `cvflow/cli/` | `cvflow` command (run / validate / nodes list) | [README](cvflow/cli/README.md) |
| `cvflow/app/` | **Phase 1 PySide6 GUI** (bespoke editor, PySide6-only) | [README](cvflow/app/README.md) · docs/05 |
| `tests/` | 122 tests incl. offscreen GUI smoke + 1080p engine and param-to-pixel gates | [README](tests/README.md) |
| `examples/` | demo workflow + programmatic graph-building reference | [README](examples/README.md) |

## Hard rules (break these and the architecture rots)

1. **Import layering:** `core` imports stdlib/numpy/cv2 only · `engine` imports `core` ·
   node modules import `cvflow.sdk` only · **only `cvflow/app/` imports Qt** — no Qt
   anywhere else (docs/01 §3). The app drives the engine through the same public
   surface the CLI uses; it never reaches around the API.
2. **Outputs are immutable.** Nodes never mutate inputs; produce outputs via
   `ImageBuffer(...)` or `input.derive(...)` (arrays are frozen — violations throw).
3. **Side-effect nodes** (`side_effect = True`) only run when armed — never on a
   preview/tuning run.
4. **Nodes are pure** w.r.t. (params, inputs, external_state) — that's what makes the
   fingerprint cache correct. Anything nondeterministic sets `cacheable = False`.
5. **Every new node** gets `@node(id=..., category=..., doc=...)`, labels/tooltips on
   params, and a test in `tests/test_nodes.py` (the conformance sweep checks spec
   completeness automatically).
6. **Tests stay green** (`pytest` before claiming work done), including
   `test_benchmark.py` — the incremental-execution promise is asserted there.

## Documentation duty (owner's standing instruction)

After completing any meaningful chunk of work you MUST update:
- **STATUS.md** — mark what's done, adjust "Next steps";
- the **README.md of any package you touched** (or create one for a new package);
- `docs/` only if a *design decision* changed (note the change inline).

This is how the next session (or the next person) knows where things stand. The owner
explicitly requires these .md breadcrumbs — don't skip them.

## Writing a node (10-second reference)

```python
from cvflow.sdk import Node, node, ImageIn, ImageOut, IntParam

@node(id="cvflow.filters.median_blur", category="Filtering", label="Median Blur",
      doc="Median filter; strong salt-and-pepper noise removal.")
class MedianBlur(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")
    kernel = IntParam("Kernel size", default=5, min=1, max=99, step=2, odd_only=True)

    def process(self, ctx):
        import cv2
        ctx.outputs.out = ctx.inputs.image.derive(
            cv2.medianBlur(ctx.inputs.image.data, ctx.params.kernel))
```

Drop the file in the right `cvflow/nodes/<pack>/`, it is auto-discovered. Test with
`run_node` from `cvflow.sdk.testing`.
