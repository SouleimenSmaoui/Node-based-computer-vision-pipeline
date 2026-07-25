"""Workflow file format v1 (docs/06 §1).

Workflows are documents: human-readable JSON, stable node ids, rounded
positions, engine data (`graph`) separated from GUI data (`ui`). Loading is
permissive where safe (issues list) and strict where lying would corrupt
results (unknown node types raise — placeholder nodes are a Phase 1 feature).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cvflow.core.errors import (
    ConnectionTypeError,
    CycleError,
    GraphError,
    ParamError,
    UnknownNodeTypeError,
    WorkflowFormatError,
)
from cvflow.core.graph import Graph
from cvflow.core.registry import NodeRegistry

FORMAT_NAME = "cvflow-workflow"
SCHEMA_VERSION = 1


@dataclass
class LoadResult:
    graph: Graph
    metadata: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    base_dir: str | None = None


def save_workflow(
    graph: Graph,
    path: str | Path,
    *,
    metadata: dict[str, Any] | None = None,
    ui: dict[str, Any] | None = None,
) -> None:
    meta = dict(metadata or {})
    meta.setdefault("created", _now())
    meta["modified"] = _now()

    nodes = []
    for inst in graph.nodes.values():
        spec = inst.spec
        entry: dict[str, Any] = {
            "id": inst.id,
            "type": spec.type_id,
            "version": spec.version,
            "pos": [round(inst.pos[0], 1), round(inst.pos[1], 1)],
            "params": {p.name: p.to_json(inst.params.get(p.name)) for p in spec.params},
        }
        if inst.label and inst.label != spec.label:
            entry["label"] = inst.label
        if inst.disabled:
            entry["flags"] = {"disabled": True}
        nodes.append(entry)

    doc = {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "metadata": meta,
        "graph": {
            "nodes": nodes,
            "edges": [
                {"from": [e.src[0], e.src[1]], "to": [e.dst[0], e.dst[1]]}
                for e in graph.edges
            ],
        },
        "ui": ui or {},
    }

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: a crash mid-save can never truncate the original (docs/06 §3).
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(target)


def load_workflow(path: str | Path, registry: NodeRegistry) -> LoadResult:
    source = Path(path)
    if not source.is_file():
        raise WorkflowFormatError(f"workflow file not found: {source}")
    try:
        doc = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowFormatError(f"{source.name}: not valid JSON — {exc}") from exc

    if doc.get("format") != FORMAT_NAME:
        raise WorkflowFormatError(
            f"{source.name}: not a {FORMAT_NAME} file (format={doc.get('format')!r})")
    version = doc.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise WorkflowFormatError(f"{source.name}: missing/invalid schema_version")
    if version > SCHEMA_VERSION:
        raise WorkflowFormatError(
            f"{source.name}: schema_version {version} is newer than this build "
            f"supports ({SCHEMA_VERSION}) — update CVFlow")
    # version < SCHEMA_VERSION: run the migration chain (io/migrations, none yet).

    result = LoadResult(
        graph=Graph(),
        metadata=dict(doc.get("metadata") or {}),
        ui=dict(doc.get("ui") or {}),
        base_dir=str(source.parent),
    )
    graph_doc = doc.get("graph") or {}

    for entry in graph_doc.get("nodes", ()):
        nid, type_id = entry.get("id"), entry.get("type")
        if not nid or not type_id:
            raise WorkflowFormatError(f"{source.name}: node missing id/type: {entry}")
        spec = registry.get(type_id, entry.get("version"))  # may raise UnknownNodeTypeError

        params: dict[str, Any] = dict(entry.get("params") or {})
        stored_version = entry.get("version", spec.version)
        if stored_version != spec.version:
            params = spec.node_class.migrate_params(stored_version, params)
            result.issues.append(
                f"node {nid}: migrated params {type_id} {stored_version} → {spec.version}")
        known = {p.name for p in spec.params}
        dropped = sorted(set(params) - known)
        if dropped:
            result.issues.append(f"node {nid}: dropped unknown param(s) {dropped}")
            params = {k: v for k, v in params.items() if k in known}
        params = {k: _from_json(spec, k, v, nid, result) for k, v in params.items()}

        pos = entry.get("pos") or [0.0, 0.0]
        try:
            result.graph.add_node(
                spec, params=params, node_id=nid,
                pos=(float(pos[0]), float(pos[1])), label=entry.get("label", ""))
        except (ParamError, GraphError) as exc:
            raise WorkflowFormatError(f"{source.name}: node {nid}: {exc}") from exc
        if (entry.get("flags") or {}).get("disabled"):
            result.graph.nodes[nid].disabled = True

    for edge in graph_doc.get("edges", ()):
        try:
            src, dst = edge["from"], edge["to"]
            result.graph.connect(src[0], src[1], dst[0], dst[1])
        except (KeyError, IndexError, TypeError):
            result.issues.append(f"skipped malformed edge entry: {edge}")
        except (ConnectionTypeError, CycleError, GraphError) as exc:
            result.issues.append(f"skipped edge {edge.get('from')}→{edge.get('to')}: {exc}")

    return result


def _from_json(spec, name: str, raw: Any, nid: str, result: LoadResult) -> Any:
    param = next(p for p in spec.params if p.name == name)
    try:
        return param.from_json(raw)
    except ParamError as exc:
        result.issues.append(f"node {nid}: param {name}={raw!r} invalid ({exc}); "
                             f"using default {param.default!r}")
        return param.default


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
