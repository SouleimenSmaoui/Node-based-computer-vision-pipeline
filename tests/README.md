# tests

Run: `.venv\Scripts\python.exe -m pytest` (from repo root). Headless — the GUI tests
use `QT_QPA_PLATFORM=offscreen` and skip if PySide6 is absent, so no display is ever
needed. **184 tests, ~2 s total.**

| File | Covers |
|---|---|
| `conftest.py` | test node types (Source/Add/Mean/Fail with call counters), `chain_graph` fixture, counter reset |
| `test_core.py` | param clamp/snap/reject; the tuple params (`Range`/`Point`/`Rect`/`Color`) — band swapping, rect normalization, `clip_to`, CLI parsing, and JSON round-trips that must restore **tuples**; frozen ImageBuffer; connection rules (coerce/reject+hint); cycle rejection; topo order; replace-on-reconnect |
| `test_engine.py` | **the product promises**: second run = all cache hits; param change re-runs only downstream (asserted via call counters AND statuses); **params-snapshot coherence** (CODE_REVIEW §1.1 — a mid-dispatch edit must not leave a cache entry whose pixels disagree with its key); **demand is static** (a `Switch` does *not* make its unselected branch free); error isolation (descendants BLOCKED, siblings OK); unarmed sink writes nothing; cache eviction respects budget + pins; parallel == inline |
| `test_nodes.py` | conformance sweep over every registered node (spec completeness, default validity) + per-node behaviour + input-mutation guard. Behaviour means the property that matters — bilateral preserves more edge energy than a box blur, Sobel-x fires on a vertical edge while Sobel-y reads zero, four quarter-turns are the identity, `0 − 20` saturates to 0 rather than wrapping to 236 |
| `test_workflow_json.py` | roundtrip fidelity, permissive-load issues (unknown param/edge/value), strict refusals (unknown type, newer schema) |
| `test_cli.py` | end-to-end `run`/`validate`/`nodes list`, scalar **and tuple** param overrides (`--set crop.rect=8,8,32,24`), dry run, friendly errors, exit codes |
| `test_benchmark.py` | engine latency gate: warm 1080p param change must stay incremental and < 150 ms (measured ~6 ms on the dev machine, 2026-06-12) |
| `test_app_smoke.py` | **GUI (offscreen, skipped without PySide6):** `ImageBuffer→QImage` conversion + normalization; auto-inspector builds a widget per ParamSpec, including the five tuple/colour/code editors; armed-run handling (CODE_REVIEW §1.2 — `_armed` published under the lock, superseded runs re-arm their unfinished sinks); profiler sorts numerically, not lexically; **param-to-pixel latency** unit tests plus a 1080p end-to-end gate; log handlers don't accumulate across windows; category colours are stable across processes; and the full loop — open `edges_demo`, background run reaches Viewer A, a param change reruns incrementally, add+connect via the scene materializes an edge |

## Conventions

- Engine tests use `workers=0` (inline, deterministic) except the parallel-vs-inline
  equivalence test.
- When adding a node, add behaviour tests here — the conformance sweep only checks
  that the *spec* is complete, never that the node does the right thing.
- **A regression test is only worth having if it fails on the un-fixed code.** Every
  fix in this session was verified that way: revert the source file, watch the new
  test fail, restore. It caught one test that passed against the bug it was meant to
  catch — the default 8-px `checker_image` survives a 0.5 resize under every
  interpolation mode, so proving `Resize` mangles BINARY masks needs `cell=1`.
- Never let a modal dialog open in a headless test (`QMessageBox`, `QColorDialog`,
  `QFileDialog`) — offscreen, it blocks forever. `mark_clean()` before closing a
  window is the pattern for the "discard changes?" prompt.
- Timing-sensitive gates carry deliberately loose budgets so CI variance can't flake
  them; they exist to catch gross regressions, not to certify a number. The
  certifying measurements live in STATUS.md.
