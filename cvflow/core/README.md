# cvflow.core — the model

Pure data model: graphs, node specs, ports, params, value types.
**May import:** stdlib, numpy, cv2. **Never:** Qt, engine, io, app.

| File | Contents |
|---|---|
| `graph.py` | `Graph` (nodes+edges, connect-time cycle/type validation, replace-on-reconnect inputs, ancestors/descendants/topo, listener callbacks), `NodeInstance`, `Edge` |
| `node.py` | `Node` base (lifecycle: setup/process/teardown; flags: side_effect/stateful/cacheable/parallel_unsafe), `@node` decorator → `NodeSpec`, `Issue` |
| `ports.py` | `PortDecl` descriptor + factories (`ImageIn/Out`, `ContoursIn/Out`, `NumberIn/Out`, `TextIn/Out`, `AnyIn/Out`) |
| `params.py` | `ParamSpec` descriptors (Int/Float/Bool/Enum/String/Path); policy: snap-to-valid (clamp/odd), raise on type mismatch |
| `registry.py` | `NodeRegistry` (type id → versions → spec; search; categories) |
| `types/image.py` | `ImageBuffer` (frozen ndarray + ColorSpace + range + meta; `derive()`), BGR-canonical policy |
| `types/base.py` | `PortType` + `check_connection` (Ok/Coerce/Reject), runtime checks, `nbytes_of`/`summary_of` |
| `types/geometry.py` | `ContourSet` (more geometry types land with their producer nodes) |
| `errors.py` | exception taxonomy |

Invariants this package owns: connections are validated when drawn, not when run;
declaration order of ports/params is preserved (drives UI layout later); arrays inside
published values are read-only.

Design: docs/01 §4, docs/03, docs/04. Next here: RangeParam/RectParam/PointParam/
CodeParam (Phase 1 inspector work), `Detections`/`Tensor` types (with ML nodes).
