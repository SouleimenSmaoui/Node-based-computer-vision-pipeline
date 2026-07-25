# cvflow.sdk — the public node-authoring API

The **only** module node packs and external plugins may import. Everything re-exported
here is the compatibility surface (semver promise from 1.0 — docs/01 N10). Internals
may be refactored freely; this façade may not break.

- `__init__.py` — re-exports: `node`, `Node`, `Issue`, port factories, param specs,
  `ImageBuffer`, `ColorSpace`, `ContourSet`, `resolve_path`, error types.
- `testing.py` — `run_node()` (builds a real ExecutionContext: validation, freezing,
  error mapping — no engine/graph needed) + synthetic images (`checker_image`,
  `gradient_image`, `blank_image`, `shapes_image`).

`run_node` **assembles inputs exactly as the engine does**: every declared port is
passed, using `None` for one you didn't supply, and an undeclared input name is an
error rather than silently ignored. That fidelity is the whole point of the harness —
before 2026-07-25 it left unsupplied optional ports *absent*, so a node reading one
got `AttributeError` under test and `None` in production.

When testing a node that must preserve a colour-space *convention* (BINARY meaning
strictly `{0, 255}`), make the input adversarial: `checker_image(64, cell=1)`. The
default 8-px checker survives operations that in fact break the convention.

Authoring + testing reference: docs/04 (full), CLAUDE.md (10-second version).
If a node needs something not exported here, that's an SDK gap — extend the façade
deliberately, don't reach into internals from node code.
