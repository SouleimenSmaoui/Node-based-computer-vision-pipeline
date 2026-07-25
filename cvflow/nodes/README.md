# cvflow.nodes — built-in node packs

Every module here imports **`cvflow.sdk` only** (plus cv2/numpy) — the same constraint
external plugins live under (principle A5: built-ins aren't special). Files are
auto-discovered by `cvflow.plugins.loader`; adding a node = dropping a file here.

## Current packs (22 nodes)

| Pack | Nodes | Notes |
|---|---|---|
| `io/` | Load Image, Save Image | unicode-safe Windows file I/O (imdecode/imencode); Load Image implements `external_state` (mtime+size → cache invalidation); Save Image is `side_effect=True` |
| `color/` | To Gray, **In Range**, **CLAHE** | In Range bands all channels into a `BINARY` mask (`validate()` enforces low ≤ high per channel) — feed it HSV for lighting-robust hue selection. CLAHE equalizes **L in LAB** for colour input, because a per-BGR-channel curve shifts hue; it refuses spaces it cannot handle rather than mangling them |
| `filters/` | Gaussian Blur, Invert, **Median Blur**, **Box Blur**, **Bilateral Filter**, **Unsharp Mask** | Gaussian Blur is the reference node from docs/04 §1 — keep in sync with the doc. **Median is the only one that keeps a BINARY label**: a rank filter emits only values already present, whereas the four averaging/blending filters emit GRAY for BINARY input (see the space rule below) |
| `edges/` | Canny, **Sobel**, **Laplacian** | typed `Image[GRAY]` input (BGR rejected at connect with hint); Canny's `validate()` enforces low ≤ high. Sobel/Laplacian default to normalized 8-bit; turn `normalize` off for the raw signed float, labelled `ValueRange.ARBITRARY` so viewers auto-scale instead of clipping negatives to black |
| `threshold/` | Threshold | global / Otsu / adaptive-mean / adaptive-gaussian → `Image[BINARY]`; `validate()` guards adaptive block size |
| `morphology/` | Morphology | erode/dilate/open/close/gradient/tophat/blackhat × rect/ellipse/cross element; space-preserving |
| `geometry/` | Resize, **Rotate / Flip**, **Crop ROI** | Crop ROI takes a `RectParam`; 0 width/height means "to the far edge" (so the default rect is a pass-through, not an empty image) and an oversized rect is clipped rather than an error, so a fixed ROI survives a resolution change. `copy=False` shares memory with the input — still frozen, so nobody can scribble on an upstream cache entry. Resize: scale-factor or absolute w/h; interpolation dropdown. **BINARY inputs are forced to nearest-neighbour** — linear/cubic/area blend neighbours and would emit e.g. 128 under a label promising `{0, 255}`, which `ImageBuffer` does not catch (it validates dtype, not the convention). Keeping the mask a mask also keeps `Find Contours` downstream (CODE_REVIEW §2.8). Rotate / Flip never resamples, so masks and measurements survive exactly; rotation applies before the flip |
| `analysis/` | Find Contours, **Filter Contours** | Find Contours: binary → `ContourSet` (min-area filter); `BINARY` input satisfies its `GRAY` port via the subtype rule. Filter Contours bands area and aspect (`RangeParam`) with an invert toggle — threshold generously, then reject by *shape*, which is usually what makes a blob pipeline reliable. Both drop the hierarchy when filtering, since its indices refer to the unfiltered tuple |
| `draw/` | Draw Contours | image + contours → BGR; `−1` thickness fills. In the GUI a geometry output can also render as a crisp vector overlay without this node |

## MVP target (~35 nodes — docs/08 Phase 1)

**22/35 done.** Batch 1 was the subset needing no new infrastructure; then the
five missing `ParamSpec` types were written (core/README), which unblocked Crop
ROI and Filter Contours immediately. What remains:

**Pure SDK work, nothing blocking:** split/merge channels, warp affine,
perspective, overlay mask, blend, draw boxes, draw text (`ColorParam` exists
now), `util/` (switch, math, display text).

**Needs new data types first:** connected components, Hough lines/circles,
template match, bounding boxes, statistics/measurements. These emit things that
are neither images nor `ContourSet` — line segments, circles, a detections
table — so decide the types before writing the nodes (`types/geometry.py` says
the catalog "arrives with the nodes that produce them"; this is that moment).

**Needs GUI work, not node work:** pick-in-viewer for `RectParam`/`PointParam`
is a viewer→inspector gesture, not a node feature — Crop ROI is fully usable
without it, just typed numerically. The custom Script node has `CodeParam` and
its editor widget, but must set `cacheable = False` (arbitrary code is not pure)
and needs a declared-ports UI.

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
