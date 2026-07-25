# tests

Run: `.venv\Scripts\python.exe -m pytest` (from repo root). Headless — the GUI tests
use `QT_QPA_PLATFORM=offscreen` and skip if PySide6 is absent, so no display is ever
needed. 80 tests, ~1 s total.

| File | Covers |
|---|---|
| `conftest.py` | test node types (Source/Add/Mean/Fail with call counters), `chain_graph` fixture, counter reset |
| `test_core.py` | param clamp/snap/reject, frozen ImageBuffer, connection rules (coerce/reject+hint), cycle rejection, topo order, replace-on-reconnect |
| `test_engine.py` | **the product promises**: second run = all cache hits; param change re-runs only downstream (asserted via call counters AND statuses); error isolation (descendants BLOCKED, siblings OK); unarmed sink writes nothing; cache eviction respects budget + pins; parallel == inline results |
| `test_nodes.py` | conformance sweep over every registered node (spec completeness, default validity) + behavior tests per built-in node + input-mutation guard |
| `test_workflow_json.py` | roundtrip fidelity, permissive-load issues (unknown param/edge/value), strict refusals (unknown type, newer schema) |
| `test_cli.py` | end-to-end `run`/`validate`/`nodes list`, param overrides, dry run, friendly errors, exit codes |
| `test_benchmark.py` | the latency gate: warm 1080p param change must stay incremental and < 150 ms (measured ~6 ms on the dev machine, 2026-06-12) |
| `test_app_smoke.py` | **GUI (offscreen, skipped without PySide6):** `ImageBuffer→QImage` conversion + normalization, auto-inspector builds a widget per ParamSpec, and the full loop — open `edges_demo`, background run reaches Viewer A, a param change reruns incrementally (canny executes, blur cached), add+connect nodes via the scene materializes an edge item |

Conventions: engine tests use `workers=0` (inline, deterministic) except the
parallel-vs-inline equivalence test. When adding a node, add behavior tests here —
the sweep only checks the spec.
