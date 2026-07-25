# cvflow.nodes — built-in node packs

Every module here imports **`cvflow.sdk` only** (plus cv2/numpy) — the same constraint
external plugins live under (principle A5: built-ins aren't special). Files are
auto-discovered by `cvflow.plugins.loader`; adding a node = dropping a file here.

## Current packs (11 nodes)

| Pack | Nodes | Notes |
|---|---|---|
| `io/` | Load Image, Save Image | unicode-safe Windows file I/O (imdecode/imencode); Load Image implements `external_state` (mtime+size → cache invalidation); Save Image is `side_effect=True` |
| `color/` | To Gray | |
| `filters/` | Gaussian Blur, Invert | Gaussian Blur is the reference node from docs/04 §1 — keep in sync with the doc |
| `edges/` | Canny | typed `Image[GRAY]` input (BGR rejected at connect with hint), `validate()` enforces low ≤ high |
| `threshold/` | Threshold | global / Otsu / adaptive-mean / adaptive-gaussian → `Image[BINARY]`; `validate()` guards adaptive block size |
| `morphology/` | Morphology | erode/dilate/open/close/gradient/tophat/blackhat × rect/ellipse/cross element; space-preserving |
| `geometry/` | Resize | scale-factor or absolute w/h; interpolation dropdown |
| `analysis/` | Find Contours | binary → `ContourSet` (min-area filter); `BINARY` input satisfies its `GRAY` port via the subtype rule |
| `draw/` | Draw Contours | image + contours → BGR; `−1` thickness fills. In the GUI a geometry output can also render as a crisp vector overlay without this node |

## MVP target (~35 nodes — docs/08 Phase 1)

Still to add: in-range colour mask, crop-ROI (pick-in-viewer RectParam), rotate/
flip/warp/perspective, more `filters/` (median, bilateral, box, unsharp), more
`edges/` (Sobel, Laplacian), more `analysis/` (filter contours, bounding boxes,
connected components, Hough lines/circles, template match, statistics), more
`draw/` (boxes, text, overlay mask, blend), `util/` (switch, math, display text),
`script/` (custom Python). ML pack is Phase 3 (docs/11).

Per-node checklist: `@node` with id/category/doc · labeled params with tooltips and
sane ranges · outputs via `derive()` · never mutate inputs · a test in
`tests/test_nodes.py`.
