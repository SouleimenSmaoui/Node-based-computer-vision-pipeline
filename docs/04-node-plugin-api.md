# 04 — Node & Plugin Architecture

Goal: a CV engineer turns a working OpenCV snippet into a first-class node — with auto-
generated UI, validation, serialization, and caching — in **under ten minutes and ~30
lines**, without touching application code. Built-in nodes use this exact API (principle
A5), so it is guaranteed complete.

---

## 1. Anatomy of a node

```python
# my_plugin/nodes/gaussian.py
from cvflow.sdk import (Node, node, ImageIn, ImageOut, IntParam, FloatParam,
                        ColorSpace)

@node(id="acme.filters.gaussian_blur", version="1.0",
      category="Filtering", label="Gaussian Blur",
      doc="Smooths an image with a Gaussian kernel.")
class GaussianBlur(Node):
    # ── ports ────────────────────────────────────────────────
    image = ImageIn("Image")                       # any space
    out   = ImageOut("Image", same_space_as="image")

    # ── parameters (auto-generate the inspector UI) ─────────
    kernel = IntParam("Kernel size", default=5, min=1, max=99,
                      step=2, odd_only=True, widget="slider")
    sigma  = FloatParam("Sigma", default=0.0, min=0.0, max=25.0,
                        widget="slider", decimals=2,
                        tooltip="0 = derive from kernel size")

    # ── execution ────────────────────────────────────────────
    def process(self, ctx):
        img = ctx.inputs.image
        blurred = cv2.GaussianBlur(img.data, (ctx.params.kernel,)*2,
                                   ctx.params.sigma)
        # Averaging puts values between 0 and 255, so a BINARY input is no
        # longer a valid mask: emit GRAY rather than mislabel it. `derive`
        # keeps the input space when space=None.
        space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        ctx.outputs.out = img.derive(blurred, space=space)
```

> **Respect the space you emit** (added 2026-07-25 after CODE_REVIEW §2.8 found
> the same defect in `Resize`). `same_space_as=` and `derive()` propagate the
> input's `ColorSpace` *label*, and `ImageBuffer` validates only channel count
> and dtype — never a space's **convention**. So an operation that breaks one
> (BINARY meaning strictly `{0, 255}`) fails silently and propagates downstream.
> Either constrain the operation to preserve the convention, or emit the space
> you actually produced.

What the author **did not** write: inspector widgets, value clamping, odd-enforcement UI,
JSON (de)serialization, undo integration, fingerprint/caching logic, thread handling,
error trapping, the node's palette entry and search keywords. All derived from the
declaration (principle A2).

### 1.1 Declarative vocabulary

**Ports** — `ImageIn/Out(label, space=None, optional=False, variadic=False)`,
`MaskIn/Out`, `ContoursIn/Out`, `DetectionsIn/Out`, `NumberIn/Out`, `TextIn/Out`,
`TableOut`, `TensorIn/Out`, `AnyIn/Out`. `same_space_as=` propagates the resolved input
space to the output type for correct downstream checking of pass-through filters.

**Parameters → widget mapping** (override with `widget=`):

| ParamSpec | Default widget | Notes |
|---|---|---|
| `IntParam` | slider + spinbox combo | `odd_only`, `step`, `suffix="px"` |
| `FloatParam` | slider + spinbox | `decimals`, log-scale option for σ-like params |
| `BoolParam` | checkbox | |
| `EnumParam` | dropdown | from `Enum` or list of (value,label) |
| `StringParam` | line edit | |
| `PathParam` | file/dir picker | `mode="open"/"save"/"dir"`, `filter="*.png *.jpg"` |
| `RangeParam` | dual-handle range slider | e.g. Canny low/high, InRange bounds |
| `PointParam` / `RectParam` | numeric fields **+ pick-in-viewer** | viewer enters pick mode; this is how Crop ROI / Perspective corners are set interactively |
| `ColorParam` | color swatch | draw nodes |
| `CodeParam` | code editor dialog | Custom Script |

Common options: `default, min, max, label, tooltip, visible_if("other_param", value)`
(conditional UI, e.g. sigma hidden when "auto" checked), `promotable=True` (can become an
input port, docs/03 §5), `live=False` (param changes don't auto-rerun — for expensive
toggles).

### 1.2 Node-level declarations

```python
class MyNode(Node):
    side_effect = True      # writes to the world → runs only when armed (docs/02 §6.1/§7.4)
    stateful    = True      # per-frame state; sequential execution (docs/02 §7.3)
    cacheable   = False     # nondeterministic output
    parallel_unsafe = True  # wraps a non-thread-safe lib
    def validate(self, params) -> list[Issue]: ...   # cross-param checks → amber badge
    def setup(self, ctx): ...      # once before first run (load model, open device)
    def teardown(self, ctx): ...   # on removal / app close / stream stop
    def on_param_changed(self, name, ctx): ...  # rare: dynamic port reconfiguration
```

Lifecycle: `__init__` (cheap, no I/O) → `setup` (lazy, first execution; heavy imports go
here — keeps app startup under N7) → `process` × N → `teardown`. The engine guarantees
setup/teardown pairing and isolates exceptions from each phase into node-level errors.

## 2. Plugin discovery

Three sources, merged into one `NodeRegistry` at startup:

1. **Built-in packs** — `cvflow.nodes.*`, scanned by import.
2. **Installed packages** — Python entry points, group `"cvflow.nodes"`:

   ```toml
   # pyproject.toml of a plugin distribution
   [project.entry-points."cvflow.nodes"]
   acme_filters = "acme_cvflow.nodes"      # module whose import registers @node classes
   ```

   *Why entry points:* it is the standard Python plugin mechanism — `pip install
   cvflow-plugin-acme` and the nodes appear; versioning, dependencies, and distribution
   ride on normal packaging infrastructure instead of a bespoke plugin manager.
3. **User plugins folder** — `~/.cvflow/plugins/**/*.py` (and per-project
   `./cvflow_plugins/`), imported at startup; **Reload Plugins** action re-imports
   changed modules and refreshes specs of existing graph nodes (dev-loop convenience —
   edit node code and re-run without restarting the app).

**Failure isolation:** a plugin that raises on import is recorded as
`PluginLoadError(distribution, traceback)` and shown in a "Plugins" panel — it never
prevents app startup (N8). Two plugins claiming one node id → first wins, second reported.

**Trust model (explicit):** plugins and Custom Script execute arbitrary Python in-process.
That is the correct contract for a developer tool (same as VS Code extensions or Python
itself) — documented, surfaced with a one-time consent dialog for workflow-embedded
scripts from foreign files, and *not* sold as a sandbox (risk register docs/09 R8).

## 3. Identity, versioning, migration

- Node identity = `"<namespace>.<name>"` + integer-ish `version` (`"1.2"`); workflows
  store both (docs/06).
- Loading an older workflow with a newer node calls
  `Node.migrate_params(old_version, params) -> params` (default: keep matching names,
  default the rest, warn).
- Missing node type (plugin not installed) → the graph loads with a **placeholder node**
  preserving the original JSON blob, ports inferred from stored edges, marked
  unmistakably red. The user can install the plugin and reload losslessly. *Why:* a
  workflow file must never be destroyed or refused because of environment drift — this is
  the difference between a tool and a toy.

## 4. The Custom Script node (escape hatch)

In-app code editor (CodeParam) with a function contract:

```python
def run(ctx, image: ImageBuffer) -> dict:
    """inputs appear as kwargs; return {output_name: value}"""
    import numpy as np
    g = cv2.cvtColor(image.data, cv2.COLOR_BGR2GRAY)
    return {"out": image.derive(g, space="GRAY"),
            "mean": float(g.mean())}
```

- Input/output ports are declared in the node's inspector (name + type dropdowns), so the
  graph stays type-checked even around arbitrary code; runtime checks verify returned
  types.
- Script text is stored in the workflow JSON (self-contained experiments) — with the
  consent-on-open rule from §2.
- Errors map to node errors with the traceback pointing into the script text (line
  numbers offset-corrected, shown inline in the editor).
- *Why it must exist:* in a prototyping tool, the moment a needed node is missing, the
  user either escapes inline or abandons the tool for their editor. The script node is
  also the on-ramp: a script that stabilizes gets promoted to a plugin file by "Export as
  plugin…" scaffolding.

## 5. Dynamic ports & composite patterns

- **Variadic inputs**: `ImageIn("Images", variadic=True)` renders an expandable port list
  (Blend, Stack, Merge).
- **Param-driven ports**: `on_param_changed` may add/remove declared port groups (e.g.,
  Split Channels exposing 1/3/4 outputs by space) — the graph view updates and dangling
  edges are dropped with an undo-able warning.
- **Subgraphs (Phase 3)**: a selection collapses into a `CompositeNode` whose inner graph
  is stored in the same JSON schema (recursive), with promoted inner params as the
  composite's params. This is the reuse mechanism (team-shareable "macro" nodes) and
  deliberately reuses persistence + registry machinery rather than introducing a second
  abstraction.

## 6. Node pack guidelines (quality bar for built-ins and the example repo)

- One operation per node; prefer an `EnumParam` op-selector for true families
  (Morphology) over 6 near-identical nodes — palette stays scannable.
- Label parameters in domain language (`"Kernel size"`, not `ksize`), always with
  tooltips and sane interactive ranges (a slider to 9999 is not tuning).
- Outputs preserve metadata via `derive()`; never mutate inputs (the frozen array will
  throw anyway).
- Every node ships `doc` + at least one conformance test (see §8) + appears in exactly
  one category.

## 7. Distribution & scaffolding

`plugins-examples/cvflow-plugin-example/` in this repo is a complete pip-installable
template (pyproject, entry point, one node, one test, README). Phase 2 adds
`cvflow plugin new <name>` (cookiecutter-style) so the ten-minute promise includes
packaging. An in-app Plugin Manager (list/enable/disable/open-folder) is Phase 3 —
*not* a package index; pip remains the distribution channel (no bespoke store to build,
secure, and moderate).

## 8. Testing nodes

The SDK ships a harness so node tests need no engine, no GUI:

```python
from cvflow.sdk.testing import run_node, checker_image

def test_gaussian_smooths():
    out = run_node(GaussianBlur,
                   inputs={"image": checker_image(64, space="GRAY")},
                   params={"kernel": 9, "sigma": 2.0})
    assert out["out"].space is ColorSpace.GRAY
    assert out["out"].data.std() < checker_image(64).data.std()
```

`run_node` builds a real `ExecutionContext` (validation, freezing, error mapping
included), so a passing test means the node behaves inside the engine. The app's CI runs
a **conformance sweep**: every registered node is instantiated, spec-validated
(labels/docs/ranges present), smoke-run on type-appropriate synthetic inputs, and checked
for input mutation. Plugins get this for free via `cvflow nodes test acme.*`.
