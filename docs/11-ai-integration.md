# 11 — Scalability Plan for AI / Deep-Learning Modules

Requirement F10: YOLO, SAM, OCR, face, pose, tracking, TensorFlow/PyTorch models must
arrive later **without architectural change**. The honest test of that claim: walk each
future capability through the existing contracts and show nothing new is needed except
nodes and one service. That walk-through is this document.

## 1. Why the architecture already fits

Four earlier decisions do the heavy lifting:

1. **DL nodes are just nodes** (principle A5). A YOLO node is `setup()` (load session) +
   `process()` (infer) + params (confidence, NMS IoU, device) + typed ports. The plugin
   API was designed with `setup/teardown` lifecycle *because* of model loading.
2. **The `Detections` / `Tensor` / `Keypoints` / `Mask` types are already in core**
   (docs/03) — detector→tracker→counter→drawer chains type-check today with zero ML
   installed. Types are the interop contract; they ship in core precisely so plugins
   never need to invent private ones.
3. **`stateful` + streaming contracts** (docs/02 §7.3) already cover trackers and
   temporal models (sequential frame guarantee, state reset, cache exclusion).
4. **Extras-based packaging + lazy imports in `setup()`** keep the base app at ~200 MB
   and 3 s startup even when `cvflow[ml]` adds gigabytes of runtime.

## 2. Inference backend abstraction

The single new abstraction (lives in `nodes/ml/`, *not* in core — it is a node-pack
concern):

```python
class InferenceSession(Protocol):
    def run(self, inputs: dict[str, Tensor]) -> dict[str, Tensor]: ...
    @property def device(self) -> str: ...

class OnnxSession(InferenceSession): ...      # default — onnxruntime, EP-selectable
class TorchSession(InferenceSession): ...     # optional plugin pack (cvflow-plugin-torch)
class TFSession(InferenceSession): ...        # optional plugin pack, if ever needed
```

**ONNX Runtime is the default backbone** (docs/10): one MIT-licensed runtime executes
models exported from PyTorch, TF, and YOLO-family repos, with execution providers for
CPU, CUDA, TensorRT, and DirectML (relevant on Windows industrial boxes without NVIDIA).
Framework-native sessions exist for models that resist export (research checkpoints) but
live in separate plugin distributions so their multi-GB dependencies are strictly opt-in.

Device policy: global default (settings) + per-node override param; `Tensor.device`
travels with data so accidental CPU↔GPU ping-pong is *visible* in the data inspector and
fixable with explicit ToDevice nodes — silent transfers are the classic GPU-pipeline
perf killer.

## 3. The future node packs, mapped onto existing types

| Capability | Node(s) | Inputs → Outputs | Uses existing contract |
|---|---|---|---|
| Object detection (YOLO-ONNX, RT-DETR…) | Detect | `Image` → `Detections` | Detections type; Draw Boxes already consumes it |
| Segmentation (SAM/SAM2, semantic) | Segment / SAM Prompt | `Image` (+ `Points`/`BBoxes` prompts) → `Detections(masks)` or `Mask` | prompt ports are ordinary geometry inputs; pick-in-viewer PointParam gives interactive SAM prompting for free |
| OCR (RapidOCR) | OCR | `Image` → `Table` (text, conf, box) + `Detections` | Table feeds CSV sink unchanged |
| Classification | Classify | `Image` → `DictValue` (label→score) | inspector tree + Display Text |
| Pose | Pose | `Image` → `Keypoints` | skeleton overlay renderer exists |
| Face | Detect+Embed | `Image` → `Detections` + `Tensor` (embeddings) | embedding compare = Math/Threshold nodes |
| Tracking (ByteTrack-class) | Track | `Detections` stream → `Detections(track_id)` | `stateful=True` contract; ids flow to counter/draw nodes |
| Embeddings/similarity | Embed / Match | `Image` → `Tensor`; `Tensor×2` → `Number` | pure dataflow |

No row required a core change — that is the architectural claim, demonstrated.

## 4. ModelManager (the one new service, Phase 3)

`services/models.py`: a registry of model artifacts — `name, version, url(s), sha256,
file size, license tag` → download on first use into the user cache
(`…/cvflow/models/<name>/<hash>/`), verify hash, hand local paths to nodes
(`ctx.resources.models.get("yolox-s")`).

Why a service and not per-node downloads: dedup across nodes/workflows, integrity
verification in one audited place, offline-environment story (pre-seed the cache folder —
factories often have no internet), and license surfacing (the manager shows each model's
license before first download; weights licensing ≠ code licensing, and users must see
that — e.g. anything trained on restricted data).

Bundles record model ids+hashes, never weights (docs/06 §2).

## 5. GPU strategy (restated against expectations)

| Workload | GPU path | Status |
|---|---|---|
| DL inference | onnxruntime-gpu EPs (CUDA/TensorRT/DirectML) | the supported, clean path |
| Classic CV (filters, morphology) | stock wheels are CPU-only; CuPy node pack optional; custom `cv2.cuda` builds documented as advanced self-serve | deliberate non-promise (risk R10) |
| Display | always GPU (GL textures) | free already |

For prototyping workloads, classic-CV CPU is rarely the bottleneck once incremental
caching and proxy preview exist; inference is where GPUs pay, and that path is first-class.

## 6. Performance patterns reserved for ML nodes

- **Session warm-keeping:** `setup()` owns the session for the node's lifetime; param
  changes that don't touch the model (confidence threshold) re-run `process()` only —
  the fingerprint includes params, so threshold-only changes even hit *cached* raw
  outputs when the node splits "infer" and "filter" into two nodes (the recommended
  pack design: Detect → Filter Detections, making NMS/conf tuning cache-cheap).
- **Batch dimension:** `Tensor` carries layout; folder-batch mode may batch N images per
  `run()` where the node opts in (`batch_capable=True`) — engine groups frames, nothing
  else changes.
- **Async readiness:** streaming inference at camera rate can pipeline (frame N+1
  pre-processing while N infers) — the StreamExecutor's pump/worker split already
  permits depth-1 pipelining; declared per node, default off for latency honesty.
- **Quantization/optimization:** ModelManager variants (`yolox-s`, `yolox-s-int8`) are
  just different artifacts — a dropdown param, no machinery.

## 7. What would actually require architecture work (named honestly)

- **Training/fine-tuning loops** — out of scope by charter (docs/01 §1.4); would need
  long-running job management, dataset abstractions, experiment tracking.
- **Distributed/multi-machine execution** — the engine is single-process by design;
  scaling out is a different product (and Roboflow exists).
- **Sub-graph iteration (per-detection crops through a sub-pipeline)** — genuinely useful
  (OCR-on-each-plate); planned as the `ForEach` composite in Phase 3+ on top of subgraphs;
  the type system already supports `ListValue[Image]`, the engine needs a scoped-iteration
  plan node — bounded, designed-for, not yet built. This is the one known future engine
  extension, and it is additive.
