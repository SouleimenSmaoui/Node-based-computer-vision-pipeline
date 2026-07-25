# cvflow.core — the model

Pure data model: graphs, node specs, ports, params, value types.
**May import:** stdlib, numpy, cv2. **Never:** Qt, engine, io, app.

| File | Contents |
|---|---|
| `graph.py` | `Graph` (nodes+edges, connect-time cycle/type validation, replace-on-reconnect inputs, ancestors/descendants/topo, listener callbacks), `NodeInstance`, `Edge` |
| `node.py` | `Node` base (lifecycle: setup/process/teardown; flags: side_effect/stateful/cacheable/parallel_unsafe), `@node` decorator → `NodeSpec`, `Issue` |
| `ports.py` | `PortDecl` descriptor + factories (`ImageIn/Out`, `ContoursIn/Out`, `NumberIn/Out`, `TextIn/Out`, `AnyIn/Out`) |
| `params.py` | `ParamSpec` descriptors — scalars (Int/Float/Bool/Enum/String/Path) and tuples (`RangeParam`, `PointParam`, `RectParam`, `ColorParam`) plus `CodeParam`; policy: snap-to-valid (clamp/odd/swap), raise on type mismatch |
| `registry.py` | `NodeRegistry` (type id → versions → spec; search; categories) |
| `types/image.py` | `ImageBuffer` (frozen ndarray + ColorSpace + range + meta; `derive()`), BGR-canonical policy |
| `types/base.py` | `PortType` + `check_connection` (Ok/Coerce/Reject), runtime checks, `nbytes_of`/`summary_of` |
| `types/geometry.py` | `ContourSet` (more geometry types land with their producer nodes) |
| `errors.py` | exception taxonomy |

Invariants this package owns: connections are validated when drawn, not when run;
declaration order of ports/params is preserved (drives UI layout later); arrays inside
published values are read-only.

## The tuple-valued params (added 2026-07-25)

`RangeParam` `(low, high)` · `PointParam` `(x, y)` · `RectParam` `(x, y, w, h)` ·
`ColorParam` `(b, g, r[, a])`. Three things they all get right, and any future one
must too:

- **`from_json` restores the tuple.** JSON has no tuples, so a naive round-trip
  returns a list — and since params are hashed into the fingerprint, every reload
  would then miss the cache and re-execute the entire graph.
- **`parse()` accepts `"x,y,w,h"`** (and `:` for ranges), so `cvflow run --set
  crop.rect=8,8,32,24` works. Params reachable only from the GUI would break the
  CLI-parity promise (docs/01 §3).
- **Snap-to-valid, like the scalars.** `RangeParam` swaps a crossed band rather
  than raising; `RectParam` normalizes a negative extent into a positive one, so
  dragging a selection up-and-left just works.

`ColorParam` stores **BGR**, matching OpenCV, so a node passes the value straight to
`cv2.rectangle`. Qt is RGB — that swap lives in the inspector widget and nowhere else.
`RectParam.clip_to(value, w, h)` is what nodes should use rather than trusting a
stored rect: the ROI was picked against whatever image was displayed then.

Design: docs/01 §4, docs/03, docs/04. Next here: pick-in-viewer for `RectParam`/
`PointParam` (needs viewer→inspector wiring, docs/08 Phase 1); `Detections`/`Tensor`
types (with the Hough/template-match nodes and later the ML pack).
