# 06 — Persistence: Workflow Files, Settings, Run History

Principle: **workflows are documents** — human-readable, diffable, hand-editable,
version-controllable. JSON, one file per workflow, no database required to use the app.
Databases appear only where data is genuinely relational and append-only (run history,
Phase 3).

---

## 1. Workflow file (`*.cvflow.json`)

```json
{
  "format": "cvflow-workflow",
  "schema_version": 1,
  "app_version": "0.4.0",
  "metadata": {
    "title": "PCB solder inspection",
    "description": "Otsu + morphology + contour area gating",
    "author": "souleimen",
    "created": "2026-06-12T10:31:00Z",
    "modified": "2026-06-12T14:02:11Z",
    "tags": ["pcb", "inspection"]
  },
  "graph": {
    "nodes": [
      {
        "id": "n1",
        "type": "cvflow.io.load_image",
        "version": "1.0",
        "label": "Load board photo",
        "pos": [-420.0, 60.0],
        "params": { "path": "assets/board_07.png", "color": "BGR" },
        "flags": { "disabled": false }
      },
      {
        "id": "n7",
        "type": "cvflow.filters.gaussian_blur",
        "version": "1.0",
        "pos": [120.0, 60.0],
        "params": { "kernel": 9, "sigma": 2.0 }
      },
      {
        "id": "n9",
        "type": "acme.analysis.solder_check",
        "version": "2.1",
        "pos": [380.0, 60.0],
        "params": { "min_area": 140 }
      }
    ],
    "edges": [
      { "from": ["n1", "image"], "to": ["n7", "image"] },
      { "from": ["n7", "out"],   "to": ["n9", "image"] }
    ],
    "groups": [
      { "label": "Preprocess", "color": "#345", "nodes": ["n1", "n7"] }
    ]
  },
  "ui": {
    "viewers": [
      { "pane": "A", "watch": ["n7", "out"], "zoom": 1.0, "center": [960, 540],
        "overlays": [{ "from": ["n9", "contours"], "color": "#ff8800" }] },
      { "pane": "B", "watch": ["n9", "annotated"], "linked": true }
    ],
    "canvas": { "zoom": 0.8, "center": [0, 60] }
  },
  "requires": {
    "plugins": { "acme-cvflow": ">=2.1" }
  },
  "assets": { "base": "." }
}
```

Design decisions:

- **`schema_version` is the contract.** The serializer refuses nothing it can migrate:
  loading runs an ordered chain of `Migration` steps (`io/migrations/v1_to_v2.py`, …),
  each a pure JSON→JSON function with tests. Saving always writes the newest schema.
  *Why explicit migrations instead of "be lenient":* leniency rots into undocumented
  dialects; migrations keep every historical file loadable forever and testable.
- **Node `type` + `version` stored per node** → per-node param migration and placeholder
  preservation for missing plugins (docs/04 §3). The `requires.plugins` block lets the
  app name what's missing up front.
- **Stable string ids** (`n1`, `n7`) not array indices → minimal, reviewable git diffs
  (moving a node changes one `pos` line; adding a node doesn't renumber the file).
  Numbers are rounded (positions 1 decimal, params as-authored) to avoid diff noise.
- **A param's `from_json` must reconstruct its exact in-memory value, not merely an
  equal-looking one** (added 2026-07-25, when the tuple params landed). JSON has no
  tuple type, so `(8, 8, 32, 24)` is written as an array and naively read back as a
  *list*. That is not cosmetic: params are hashed into every node's fingerprint
  (docs/02 §3.1), so a type change on load makes every fingerprint miss and reopening
  a workflow re-executes the entire graph instead of restoring it from cache. Any new
  `ParamSpec` whose value is not a JSON primitive needs a `from_json` that restores
  the type, and a round-trip test asserting equality *and* type.
- **`ui` is a sibling of `graph`, not mixed into it** — the engine/CLI consumes `graph`
  alone; the GUI additionally restores `ui` (open viewers, overlays, zoom). Headless
  execution provably needs no UI data (principle A1). It still lives in the *same file*
  because "reopen → my viewers are back" is core UX (docs/05 §6), and a second sidecar
  file would desynchronize.
- **Asset paths are workflow-relative** (`assets.base`), falling back to absolute with a
  portability warning on save. This makes a workflow folder copy/clone/git-able across
  machines.
- **Script bodies** (Custom Script nodes) are stored inline as JSON strings —
  self-contained experiment files trump editability of embedded code (and the in-app
  editor is the editing surface anyway). Foreign-file script consent: docs/04 §2.

### 1.1 Validation

A published JSON Schema (`docs/schema/workflow.schema.json`, generated from the
serializer's model) validates files on load and in CI; `cvflow validate <file>` is the
CLI entry. Semantic validation (types of connections, unknown params) happens on graph
construction with the same reporting path as editor-time errors.

## 2. Project bundles (`*.cvflowz`)

`File ▸ Export bundle…` zips: workflow JSON + referenced assets (rewritten to relative
paths) + a manifest (app/plugin versions, platform). Import unpacks to a chosen folder.
*Why:* "send me your exact experiment" is a one-file operation — the collaboration story
for a local-first tool. Models/weights are deliberately **not** bundled (size); the
manifest records their registry ids and hashes so ModelManager can refetch (docs/11 §4).

## 3. Autosave & crash recovery

- Journal file `<name>.cvflow.json.autosave` written atomically (temp+rename) every 60 s
  *and* after every structural edit burst, deleted on clean save/close.
- On open, a newer autosave than its base file triggers a restore prompt (N8).
- Atomic temp+rename is also how normal saves work — a crash mid-save can never truncate
  the original file.

## 4. Application settings

- **Engine/headless settings** — `cvflow.toml` in the platform config dir
  (`platformdirs`): cache budget, worker count, proxy threshold/size, plugin dirs, model
  cache dir. TOML because humans edit it and ops can deploy it; read identically by GUI
  and CLI (one behavior everywhere).
- **GUI state** — `QSettings` (native registry/plist/ini): window geometry, dock layout,
  theme, recent files, palette favorites. Disposable state goes in the disposable store;
  nothing here affects execution results.

## 5. On-disk layout summary

```
%APPDATA%/cvflow/            (platformdirs equivalent per OS)
├── cvflow.toml              # engine settings
├── plugins/                 # user plugin .py files
├── models/                  # ModelManager cache: <name>/<hash>/model.onnx + meta.json
├── logs/cvflow-YYYYMMDD.log # rotating file logs
└── history.sqlite           # Phase 3 run history (below)

<your project folder>/       # wherever the user keeps experiments
├── inspect_pcb.cvflow.json
├── assets/board_07.png
└── cvflow_plugins/          # optional per-project nodes
```

## 6. Run-history database (Phase 3, optional, SQLite)

Purpose: longitudinal questions a JSON file can't answer — "did yesterday's param change
make the pipeline slower?", "which images failed in last night's batch?".

```sql
CREATE TABLE runs (
  id INTEGER PRIMARY KEY, started_utc TEXT, mode TEXT,        -- interactive|batch|stream
  workflow_path TEXT, workflow_hash TEXT,                      -- fingerprint of graph+params
  duration_ms REAL, status TEXT, frames INTEGER, app_version TEXT
);
CREATE TABLE node_metrics (
  run_id INTEGER REFERENCES runs(id), node_id TEXT, node_type TEXT,
  ms REAL, cache_hit INTEGER, out_bytes INTEGER, error TEXT
);
CREATE TABLE batch_items (
  run_id INTEGER REFERENCES runs(id), item TEXT, status TEXT, error TEXT, ms REAL
);
```

Append-only, written by the engine's report hook, size-capped with retention pruning,
entirely optional (off by default in interactive mode, on for batch). SQLite because it
is serverless, single-file, transactional, and queryable — the correct shape for local
telemetry; nothing about workflows themselves ever moves into it.
