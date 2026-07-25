# 07 — Class Diagrams

Mermaid diagrams (render on GitHub / VS Code). These show the load-bearing classes and
relationships, not every helper. Cross-references: behavior in docs/02 (engine), docs/03
(types), docs/04 (plugin API), docs/05 (GUI).

---

## 1. Core model (`cvflow.core`)

```mermaid
classDiagram
    direction LR

    class Graph {
        +nodes: dict~NodeId, NodeInstance~
        +edges: list~Edge~
        +groups: list~Group~
        +add_node(spec, params) NodeInstance
        +remove_node(id)
        +connect(src, src_port, dst, dst_port) Edge
        +disconnect(edge)
        +ancestors(ids) set
        +descendants(ids) set
        +check_acyclic(candidate_edge) bool
        +add_listener(GraphListener)
    }

    class NodeInstance {
        +id: NodeId
        +spec: NodeSpec
        +params: ParamValues
        +pos: (float, float)
        +label: str
        +disabled: bool
        +set_param(name, value)
    }

    class Edge {
        +src: (NodeId, port_name)
        +dst: (NodeId, port_name)
        +coercion: Coercion | None
    }

    class NodeSpec {
        +type_id: str
        +version: str
        +category: str
        +label: str
        +inputs: list~PortSpec~
        +outputs: list~PortSpec~
        +params: list~ParamSpec~
        +flags: side_effect / stateful / cacheable / parallel_unsafe
        +node_class: type~Node~
    }

    class Node {
        <<abstract, authored by plugins>>
        +setup(ctx)
        +process(ctx)*
        +teardown(ctx)
        +validate(params) list~Issue~
        +migrate_params(old_version, params) dict
    }

    class PortSpec {
        +name: str
        +label: str
        +dtype: DataType
        +optional: bool
        +variadic: bool
    }

    class ParamSpec {
        <<abstract descriptor>>
        +name / label / default / tooltip
        +widget_hint: str
        +promotable: bool
        +validate(value) value
    }
    class IntParam
    class FloatParam
    class EnumParam
    class RangeParam
    class PathParam
    class RectParam
    class CodeParam

    class NodeRegistry {
        +register(NodeSpec)
        +get(type_id, version) NodeSpec
        +search(text) list~NodeSpec~
        +categories() tree
    }

    class DataType {
        +name: str
        +check(src, dst) Ok|Coerce|Reject
        +nbytes(value) int
        +summary(value) str
    }

    Graph "1" *-- "many" NodeInstance
    Graph "1" *-- "many" Edge
    NodeInstance --> NodeSpec
    NodeSpec --> "many" PortSpec
    NodeSpec --> "many" ParamSpec
    NodeSpec --> Node : instantiates
    ParamSpec <|-- IntParam
    ParamSpec <|-- FloatParam
    ParamSpec <|-- EnumParam
    ParamSpec <|-- RangeParam
    ParamSpec <|-- PathParam
    ParamSpec <|-- RectParam
    ParamSpec <|-- CodeParam
    NodeRegistry o-- NodeSpec
    PortSpec --> DataType
```

## 2. Type system payloads (`cvflow.core.types`)

```mermaid
classDiagram
    class ImageBuffer {
        +data: ndarray (frozen)
        +space: ColorSpace
        +range: ValueRange
        +frame: FrameInfo?
        +meta: Mapping
        +derive(new_data, space?) ImageBuffer
        +writable_copy() ndarray
        +nbytes / width / height / channels
    }
    class ColorSpace {
        <<enum>> BGR RGB GRAY BINARY HSV LAB BGRA
    }
    class ContourSet {
        +contours: list~ndarray~
        +hierarchy: ndarray?
        +metrics() per-contour area/perimeter/bbox
    }
    class Detections {
        +xyxy: ndarray (N,4)
        +confidence: ndarray?
        +class_id: ndarray?
        +class_names: tuple?
        +masks: list~ndarray~?
        +track_id: ndarray?
        +filter(mask) Detections
    }
    class Tensor {
        +data: ndarray
        +layout: NCHW|NHWC|...
        +device: cpu|cuda:n
    }
    class Table {
        +rows: list~dict~
        +columns: list~str~
    }
    ImageBuffer --> ColorSpace
```

## 3. Engine (`cvflow.engine`)

```mermaid
classDiagram
    direction TB

    class ExecutionService {
        +set_observed(map)
        +notify_param(node_id)
        +notify_topology()
        +request_run(scale?) generation
        +arm_sinks(ids) / run_batch(opts)
        +start_stream(source_id) / stop_stream()
        +hooks: EngineHooks
    }

    class Scheduler {
        +build_plan(graph, observed, cache) ExecutionPlan
        +run(plan, pool, token, hooks)
    }
    class ExecutionPlan {
        +ordered: list~NodeId~
        +indegree: dict
        +generation: int
    }
    class OutputCache {
        +get(Fingerprint) outputs?
        +put(Fingerprint, outputs, nbytes)
        +pin(Fingerprint) / unpin
        +budget_bytes: int
        +stats() CacheStats
    }
    class Fingerprint {
        +of_node(node, input_fps) bytes
        <<BLAKE2b over type, version, params, input fps>>
    }
    class ExecutionContext {
        +inputs / params / outputs
        +log / progress(x) / is_cancelled()
        +state: dict   (stateful nodes)
        +frame: FrameInfo?
        +scale: float?
        +resources: ResourceHub
    }
    class CancellationToken {
        +cancelled: bool
        +cancel()
    }
    class StreamExecutor {
        +source: StreamSource
        +queue: BoundedQueue (drop-oldest)
        +pump() / stop()
        +stats: fps_in / fps_out / dropped
    }
    class StreamSource {
        <<interface>>
        +open() / read() Frame|EOS / close()
        +caps: seekable, fps, size
    }
    class RunReport {
        +generation / wall_ms / mode
        +nodes: dict~NodeId, NodeMetrics~
        +errors: list~NodeError~
        +cache_stats
    }
    class EngineHooks {
        +on_node_status(cb)
        +on_outputs(cb)
        +on_report(cb)
        +on_stream_stats(cb)
    }

    ExecutionService --> Scheduler
    ExecutionService --> OutputCache
    ExecutionService --> StreamExecutor
    ExecutionService --> EngineHooks
    Scheduler --> ExecutionPlan
    Scheduler --> ExecutionContext : per node
    Scheduler --> CancellationToken
    OutputCache --> Fingerprint
    StreamExecutor --> StreamSource
    Scheduler --> RunReport
```

## 4. Plugins & persistence

```mermaid
classDiagram
    class PluginLoader {
        +load_builtin()
        +load_entry_points("cvflow.nodes")
        +load_user_dirs(paths)
        +reload_changed()
        +failures: list~PluginLoadError~
    }
    class WorkflowSerializer {
        +save(graph, ui, path)
        +load(path) (graph, ui, issues)
        +schema_version: int
    }
    class Migration {
        <<one per schema bump>>
        +from_version / to_version
        +apply(json) json
    }
    class AssetResolver {
        +resolve(rel_path, base) abs_path
        +make_relative(abs, base) rel
        +bundle(graph, out_zip)
    }
    class SessionService {
        +open(path) Document
        +save / autosave_tick
        +recover() list~Document~
    }
    PluginLoader --> NodeRegistry : registers
    WorkflowSerializer --> Migration : chains
    WorkflowSerializer --> NodeRegistry : resolves types
    SessionService --> WorkflowSerializer
    SessionService --> AssetResolver
```

## 5. GUI (Qt layer — adapters around the headless core)

```mermaid
classDiagram
    direction TB
    class MainWindow {
        +docks: palette, inspector, viewers, console, profiler
        +actions / command palette
    }
    class GraphController {
        +mediates Graph <-> GraphViewPort
        +undo_stack: QUndoStack
        +commands: AddNode, Connect, SetParam, ...
    }
    class ExecutionController {
        +debounce(30ms) + supersede
        +observed set from viewers
        +adapts EngineHooks -> Qt signals
        +proxy-mode policy
    }
    class GraphViewPort {
        <<interface — NodeGraphQt today, custom later>>
        +add_node / remove / connect
        +set_badge(node, status, ms)
        +set_heat(node, fraction)
        +events: node_moved, wire_drawn, selection
    }
    class NodeGraphQtAdapter
    class InspectorPanel {
        +build_for(NodeInstance)  // ParamSpec -> QWidget factory
    }
    class ViewerPanel {
        +watch(node, port)
        +ImageView (GL canvas, zoom/pan/probe)
        +OverlayLayerStack
        +link_group
    }
    class ConsolePanel
    class ProfilerPanel
    class PalettePanel

    MainWindow --> GraphController
    MainWindow --> ExecutionController
    MainWindow --> InspectorPanel
    MainWindow --> ViewerPanel
    MainWindow --> ConsolePanel
    MainWindow --> ProfilerPanel
    MainWindow --> PalettePanel
    GraphController --> GraphViewPort
    GraphViewPort <|.. NodeGraphQtAdapter
    GraphController --> Graph : edits (core)
    ExecutionController --> ExecutionService : drives (engine)
    ViewerPanel --> ExecutionController : registers demand
```

## 6. Sequence — a slider movement (the core loop, end to end)

```mermaid
sequenceDiagram
    participant W as Slider widget (GUI)
    participant IC as InspectorPanel
    participant GC as GraphController
    participant XC as ExecutionController
    participant ES as ExecutionService (engine thread)
    participant CA as OutputCache
    participant WK as Worker pool
    participant V as ViewerPanel

    W->>IC: valueChanged(9 → 11)
    IC->>GC: SetParamCommand (coalesced into drag macro)
    GC->>ES: notify_param(n7)  [dirty: n7..n10]
    IC->>XC: param edited
    XC->>XC: debounce 30 ms, cancel generation 411
    XC->>ES: request_run(scale=proxy?) → generation 412
    ES->>ES: plan = demand ∩ dirty = [n7, n9]
    ES->>CA: fp(n7)? miss · fp(n9)? miss (upstream n1..n5 hits)
    ES->>WK: process n7 → publish, then n9
    WK-->>ES: outputs + metrics
    ES->>CA: put(fp, outputs), pin viewed
    ES-->>XC: on_outputs / on_report (queued signal)
    XC-->>V: new ImageBuffer for (n7, out)
    V->>V: upload GL texture, redraw overlays
    XC-->>GC: badges: n7 ✓ 11.4 ms, n9 ✓ 3.1 ms
```
