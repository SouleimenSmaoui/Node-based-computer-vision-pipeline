# cvflow.io — persistence

| File | Contents |
|---|---|
| `workflow_json.py` | workflow file format v1: `save_workflow` (atomic temp+rename, stable ids, rounded positions, `graph`/`ui` separation), `load_workflow` → `LoadResult(graph, metadata, ui, issues, base_dir)` |
| `assets.py` | `resolve_path` / `make_relative` — params store workflow-relative paths; nodes resolve them against `LoadResult.base_dir` at run time |

Loading policy (docs/06): permissive where safe (unknown params dropped with an issue,
bad edges skipped with an issue, invalid param values fall back to defaults), strict
where lying would corrupt results (unknown node type raises `UnknownNodeTypeError`;
newer `schema_version` than this build refuses with "update CVFlow").

Next here: `migrations/` (first needed when schema goes to v2), placeholder nodes for
missing plugins (Phase 1, GUI-driven), `.cvflowz` project bundles (Phase 2),
autosave journal (Phase 1, owned by the future `services/session.py`).
