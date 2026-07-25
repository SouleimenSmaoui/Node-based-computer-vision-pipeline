# cvflow.sdk — the public node-authoring API

The **only** module node packs and external plugins may import. Everything re-exported
here is the compatibility surface (semver promise from 1.0 — docs/01 N10). Internals
may be refactored freely; this façade may not break.

- `__init__.py` — re-exports: `node`, `Node`, `Issue`, port factories, param specs,
  `ImageBuffer`, `ColorSpace`, `ContourSet`, `resolve_path`, error types.
- `testing.py` — `run_node()` (builds a real ExecutionContext: validation, freezing,
  error mapping — no engine/graph needed) + synthetic images (`checker_image`,
  `gradient_image`, `blank_image`, `shapes_image`).

Authoring + testing reference: docs/04 (full), CLAUDE.md (10-second version).
If a node needs something not exported here, that's an SDK gap — extend the façade
deliberately, don't reach into internals from node code.
