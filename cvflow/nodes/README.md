# cvflow.nodes — built-in node packs

Every module here imports **`cvflow.sdk` only** (plus cv2/numpy) — the same constraint
external plugins live under (principle A5: built-ins aren't special). Files are
auto-discovered by `cvflow.plugins.loader`; adding a node = dropping a file here.

## Current packs (20 nodes)

| Pack | Nodes | Notes |
|---|---|---|
| `io/` | Load Image, Save Image | unicode-safe Windows file I/O (imdecode/imencode); Load Image implements `external_state` (mtime+size → cache invalidation); Save Image is `side_effect=True` |
| `color/` | To Gray, **In Range**, **CLAHE** | In Range bands all channels into a `BINARY` mask (`validate()` enforces low ≤ high per channel) — feed it HSV for lighting-robust hue selection. CLAHE equalizes **L in LAB** for colour input, because a per-BGR-channel curve shifts hue; it refuses spaces it cannot handle rather than mangling them |
| `filters/` | Gaussian Blur, Invert, **Median Blur**, **Box Blur**, **Bilateral Filter**, **Unsharp Mask** | Gaussian Blur is the reference node from docs/04 §1 — keep in sync with the doc. **Median is the only one that keeps a BINARY label**: a rank filter emits only values already present, whereas the four averaging/blending filters emit GRAY for BINARY input (see the space rule below) |
| `edges/` | Canny, **Sobel**, **Laplacian** | typed `Image[GRAY]` input (BGR rejected at connect with hint); Canny's `validate()` enforces low ≤ high. Sobel/Laplacian default to normalized 8-bit; turn `normalize` off for the raw signed float, labelled `ValueRange.ARBITRARY` so viewers auto-scale instead of clipping negatives to black |
| `threshold/` | Threshold | global / Otsu / adaptive-mean / adaptive-gaussian → `Image[BINARY]`; `validate()` guards adaptive block size |
| `morphology/` | Morphology | erode/dilate/open/close/gradient/tophat/blackhat × rect/ellipse/cross element; space-preserving |
| `geometry/` | Resize, **Rotate / Flip** | Resize: scale-factor or absolute w/h; interpolation dropdown. **BINARY inputs are forced to nearest-neighbour** — linear/cubic/area blend neighbours and would emit e.g. 128 under a label promising `{0, 255}`, which `ImageBuffer` does not catch (it validates dtype, not the convention). Keeping the mask a mask also keeps `Find Contours` downstream (CODE_REVIEW §2.8). Rotate / Flip never resamples, so masks and measurements survive exactly; rotation applies before the flip |
| `analysis/` | Find Contours | binary → `ContourSet` (min-area filter); `BINARY` input satisfies its `GRAY` port via the subtype rule |
| `draw/` | Draw Contours | image + contours → BGR; `−1` thickness fills. In the GUI a geometry output can also render as a crisp vector overlay without this node |

## MVP target (~35 nodes — docs/08 Phase 1)

**Batch 1 done (20/35).** It was chosen to need *no new infrastructure* — every
node above uses existing `ParamSpec` types and existing data types, so the whole
batch is pure SDK work. What remains does not have that property, and splits by
what it needs first:

**Needs new `ParamSpec` types + inspector widgets** (STATUS.md deviation #5 —
`RangeParam`, `RectParam`, `PointParam`, `ColorParam`, `CodeParam` are all still
unwritten): crop-ROI (pick-in-viewer `RectParam`), draw boxes / draw text
(`ColorParam`), custom Script node (`CodeParam`). Build the param types first —
they are shared, and the inspector generates their widgets automatically once
`build_param_widget` knows them.

**Needs new data types or ports:** connected components, Hough lines/circles,
template match, bounding boxes, statistics/measurements — these emit things that
are not images or `ContourSet` (line segments, circles, a detections table), so
they need the type decisions made before the nodes.

**Pure SDK work, no blockers:** split/merge channels, warp affine, perspective,
filter contours, overlay mask, blend, `util/` (switch, math, display text).

ML pack is Phase 3 (docs/11).

Per-node checklist: `@node` with id/category/doc · labeled params with tooltips and
sane ranges · outputs via `derive()` · never mutate inputs · a test in
`tests/test_nodes.py`.

**Respect the space you emit.** `derive()` keeps the input's `ColorSpace` label, and
`ImageBuffer` only validates channel count and dtype — so an operation that breaks a
space's *convention* (BINARY meaning strictly `{0, 255}`, HSV ranges, etc.) fails
silently and propagates. Either constrain the operation (as `Resize` does) or emit the
space you actually produced. When testing this, make the input adversarial: a default
8-px `checker_image` survives a 0.5 resize under every interpolation mode, so it would
have passed the buggy Resize — `cell=1` is what exposes the blending.
