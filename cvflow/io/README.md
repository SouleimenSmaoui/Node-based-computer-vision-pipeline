# cvflow.io — persistence

| File | Contents |
|---|---|
| `workflow_json.py` | workflow file format v1: `save_workflow` (atomic temp+rename, stable ids, rounded positions, `graph`/`ui` separation), `load_workflow` → `LoadResult(graph, metadata, ui, issues, base_dir)` |
| `assets.py` | `resolve_path` / `make_relative` — params store workflow-relative paths; nodes resolve them against `LoadResult.base_dir` at run time |

Loading policy (docs/06): permissive where safe (unknown params dropped with an issue,
bad edges skipped with an issue, invalid param values fall back to defaults), strict
where lying would corrupt results (unknown node type raises `UnknownNodeTypeError`;
newer `schema_version` than this build refuses with "update CVFlow").

Param values pass through `ParamSpec.to_json` / `from_json`, and `from_json` must
restore the **exact type**, not just an equal-looking value. JSON has no tuples, so a
`RectParam` naively reloads as a list — and since params are hashed into every node's
fingerprint, that turns "reopen a workflow" into "re-execute the whole graph" instead
of restoring it from cache. Asserted in `tests/test_workflow_json.py`.

Next here: `migrations/` (first needed when schema goes to v2), placeholder nodes for
missing plugins (Phase 1, GUI-driven), `.cvflowz` project bundles (Phase 2),
autosave journal (Phase 1, owned by the future `services/session.py`).
