# 03 — Data Types & Port Type System

The type system exists to kill the two classic OpenCV failure modes — *wrong channel
order* and *wrong dtype/range* — at wire-connect time instead of as silent garbage three
nodes downstream, and to tell viewers how to render any value without guessing.

---

## 1. Design rules

1. **Semantic, not structural.** `np.ndarray(H,W,3, uint8)` is structurally identical for
   BGR, RGB, HSV and LAB — semantically they are four different types. Ports declare
   semantics.
2. **Wrappers are thin.** Wrapper objects carry metadata and convenience; the payload is
   always a plain numpy array reachable as `.data` — zero-copy in and out, no custom
   array math.
3. **Strict where lossy, automatic where lossless.** Connections that lose information
   (BGR→GRAY) require an explicit node; free/cheap/lossless mismatches (GRAY→BGR
   broadcast, BINARY used as GRAY) coerce automatically with a small badge on the wire.
   *Why:* full strictness makes users hate the tool (converter-node confetti); full
   automatism reintroduces the silent bugs. The lossless/lossy line is the principled cut.
4. **Everything is inspectable and overlay-renderable.** Every type implements
   `summary() -> str` (for tooltips/inspector), `nbytes` (for the cache), and geometric
   types implement a render contract for viewer overlays.

## 2. Type catalog

| Type | Payload | Notes |
|---|---|---|
| `Image[space, depth]` | `ImageBuffer` | spaces: BGR, RGB, GRAY, BINARY, HSV, LAB, BGRA; depths: U8, U16, F32 |
| `Mask` | `ImageBuffer(BINARY,U8)` | alias type; any BINARY image connects to Mask ports |
| `Contours` | `ContourSet` — list of (N,1,2) int arrays + hierarchy | exactly what `cv2.findContours` yields, plus per-contour cached metrics |
| `Points` / `Lines` / `Polygons` / `Circles` | dataclass lists | Hough outputs, ROI tools |
| `Keypoints` | named landmark sets (N,2 float + names/conf) | pose, facial landmarks |
| `BBoxes` | (N,4) float xyxy + optional scores/labels | classic detection geometry |
| `Detections` | boxes + scores + class ids/names + optional masks + optional track ids | the composite ML currency — one type for YOLO/SAM/trackers (see docs/11) |
| `Tensor` | ndarray + layout (NCHW/NHWC/…) + device (cpu/cuda:n) + dtype | pre/post-processing for ML nodes |
| `Features` | descriptors (N,D) + keypoints | ORB/SIFT matching chains |
| `Number`, `Text`, `Bool` | scalars | thresholds, measurements, labels |
| `ListValue`, `DictValue` | JSON-able containers | metadata, stats, OCR results |
| `Table` | list of dict rows + column order | feeds CSV/JSON writers cleanly |
| `Any` | — | utility nodes only (Switch, Probe); connects to everything, checked at runtime |

All geometric types live in **image pixel coordinates** of the image they were derived
from and carry an optional `ref_size=(w,h)`; the overlay renderer rescales when drawn on
a differently-sized image and warns on mismatch. *Why:* coordinate-frame confusion is the
geometry equivalent of the BGR/RGB bug.

## 3. `ImageBuffer`

```python
@dataclass(frozen=True)
class ImageBuffer:
    data:  np.ndarray            # frozen: data.flags.writeable == False
    space: ColorSpace            # BGR | RGB | GRAY | BINARY | HSV | LAB | BGRA
    range: ValueRange = U8_FULL  # semantic range, e.g. F32 images may be 0..1
    frame: FrameInfo | None = None   # index, timestamp, source id (streams)
    meta:  Mapping = EMPTY       # free-form provenance (exposure, filename, …)

    # helpers
    def derive(self, new_data, *, space=None) -> ImageBuffer   # inherit meta, freeze
    def writable_copy(self) -> np.ndarray
    @property nbytes; width; height; channels
    def summary(self) -> str     # "BGR u8 1920×1080, 5.9 MB, frame 214"
```

Decisions:

- **Frozen + read-only array** enforces the engine's immutability contract mechanically
  (docs/01 §6.1). `derive()` is the blessed way to produce outputs — it propagates
  metadata so provenance survives a 15-node chain.
- **Canonical channel order is BGR** (OpenCV-native). Every wrapped `cv2.*` call runs
  copy-free; RGB exists as a type for sources/sinks that are natively RGB (PIL,
  screenshots, some cameras) and for ML nodes that need RGB input. The *viewer* converts
  to RGB only at display time (one conversion per displayed frame, amortized on the GUI
  side). *Why not canonical RGB:* it would put a hidden `cvtColor` around nearly every
  OpenCV node — the common path must be the free path.
- **BINARY is a distinct space**, not "GRAY that happens to be 0/255": morphology,
  contours and mask logic *require* binary input, and the type system can now enforce it.
  Coercion BINARY→GRAY is free; GRAY→BINARY requires a Threshold node (lossy, parametric).

  > **Correction (2026-07-25).** "The type system can enforce it" is only half true,
  > and the half that isn't cost us two real bugs. `ImageBuffer` validates the
  > *channel count* and the *dtype* of a BINARY image — it does **not** and cannot
  > cheaply validate the `{0, 255}` **convention**, which would mean scanning every
  > pixel on every construction. So an operation that blends neighbours (resize,
  > blur, warp) happily emits 128s still labelled BINARY, and nothing downstream
  > objects. Found in `Resize` (CODE_REVIEW §2.8) and then in `GaussianBlur` — which
  > was the reference example in docs/04 §1, so the defect was being copied into
  > every new node pack.
  >
  > The rule, now stated in docs/04 §1 and enforced by node tests: **either constrain
  > the operation to preserve the convention** (Resize and the warps force
  > nearest-neighbour on BINARY; rank filters and bitwise ops preserve it for free)
  > **or emit the space you actually produced** (the averaging filters emit GRAY).
  > A space's *invariants* are the node author's responsibility; only its *shape* is
  > the type system's.
- **Float images** declare their semantic `range` (0..1, 0..255, arbitrary). Viewers use
  it for correct display normalization (with a false-color/auto-gain option for
  arbitrary-range data like gradients), instead of the classic all-white float display bug.

## 4. Detections (the ML currency)

```python
@dataclass(frozen=True)
class Detections:
    xyxy: np.ndarray            # (N,4) float32
    confidence: np.ndarray | None   # (N,)
    class_id: np.ndarray | None     # (N,) int
    class_names: tuple[str, ...] | None
    masks: list[np.ndarray] | None  # per-instance bool masks (or RLE later)
    track_id: np.ndarray | None     # (N,) int — filled by tracker nodes
```

One composite type — deliberately mirroring the shape of `supervision.Detections`, the
de-facto community convention — means *any* detector plugs into *any* tracker, filter,
counter, or drawer node without adapter nodes. This single decision is most of what
"future YOLO/SAM/tracking without architectural change" requires (docs/11).

## 5. Parameters are not ports

Parameters (slider/spinbox/dropdown values) are node-local configuration, serialized with
the workflow and fingerprinted (docs/02 §3.1). Ports move per-execution data. A parameter
may be **promoted to an input port** (e.g., feed a measured `Number` into Threshold's
value) — the inspector offers "expose as input" on parameters declared `promotable=True`.
*Why the separation:* it keeps graphs visually quiet (sliders don't appear as wires) while
allowing dataflow control when an experiment needs it.

## 6. Connection validation & coercion

On wire creation `Graph` asks the registry:

```python
def check(src: PortType, dst: PortType) -> Ok | Coerce(fn, badge) | Reject(reason)
```

- **Exact / subtype match → Ok.** (`Image[BINARY]` satisfies `Image[GRAY]` consumers,
  `Mask` ports accept BINARY images, `Detections` satisfies `BBoxes` consumers by
  projection.)
- **Registered coercion → Coerce.** Auto-inserted adapter, shown as a small dot-badge on
  the wire with a tooltip ("auto: GRAY→BGR replicate"). Registered coercions: GRAY→BGR/RGB
  (replicate), BINARY→GRAY (identity), U8→F32 (scale to range), BBoxes→Detections (wrap),
  Image→Tensor (HWC→layout per consumer hint).
- **Anything else → Reject** with a human reason rendered as a red wire preview + status
  text: `Canny expects Image[GRAY]; got Image[BGR] — insert "To Gray"`. Rejections name
  the fixing node; the editor offers right-click → auto-insert it.

Runtime re-validation still occurs in `ctx` (cheap asserts) because `Any`-typed utility
nodes and Custom Script outputs are only checkable at run time.

## 7. Display & inspection contracts

| Contract | Used by | Examples |
|---|---|---|
| `to_display(value) -> RGB ndarray` | viewers | space conversion, float normalization, mask tinting |
| `to_overlay(value, style) -> OverlayBatch` | viewer overlay layer | contours→polylines, Detections→rects+labels+mask tint, Keypoints→markers+skeleton |
| `summary(value) -> str` | tooltips, node hover, console | "Detections: 12 objects, 3 classes" |
| `to_tree(value) -> InspectorTree` | data inspector panel | dict/list drill-down, array stats (shape, dtype, min/max/mean) |
| `to_json(value)` / `to_rows(value)` | JSON/CSV exporters | Detections→rows, measurements→rows |

These are registered per type in the core (`to_display`/`to_json`) and per type in the
app layer (`to_overlay` Qt renderers) — keeping core Qt-free while making every type
viewable, inspectable, and exportable by construction. A new plugin type that registers
these contracts gets full GUI support without touching the GUI.
