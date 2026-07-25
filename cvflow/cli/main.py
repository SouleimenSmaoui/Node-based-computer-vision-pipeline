"""Headless CLI (docs/01 layer diagram): run, validate, nodes list.

The CLI is the proof that the core is headless — it drives the exact engine
the GUI will drive, through the same public surface.

    cvflow run workflow.cvflow.json --set n3.kernel=9 --profile
    cvflow validate workflow.cvflow.json
    cvflow nodes list
"""

from __future__ import annotations

import argparse
import logging
import sys

from cvflow.core.errors import CVFlowError, ParamError
from cvflow.core.types.base import summary_of
from cvflow.engine import EngineSettings, ExecutionService
from cvflow.engine.context import Resources
from cvflow.io.workflow_json import load_workflow
from cvflow.plugins import builtin_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cvflow", description="CVFlow headless workflow runner")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="execute a workflow")
    p_run.add_argument("workflow")
    p_run.add_argument("--set", action="append", default=[], metavar="NODE.PARAM=VALUE",
                       help="override a parameter (repeatable)")
    p_run.add_argument("--target", action="append", default=[], metavar="NODE_ID",
                       help="observe this node's outputs (repeatable); "
                            "default: all sink nodes")
    p_run.add_argument("--no-sinks", action="store_true",
                       help="do not arm side-effect nodes (dry run)")
    p_run.add_argument("--profile", action="store_true",
                       help="print the per-node execution report")
    p_run.add_argument("--workers", type=int, default=None,
                       help="worker threads (0 = inline)")

    p_val = sub.add_parser("validate", help="check a workflow file")
    p_val.add_argument("workflow")

    p_nodes = sub.add_parser("nodes", help="inspect available node types")
    nodes_sub = p_nodes.add_subparsers(dest="nodes_command", required=True)
    nodes_sub.add_parser("list", help="list registered nodes by category")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s")

    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "nodes":
            return _cmd_nodes_list()
    except CVFlowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _load(path: str):
    registry, failures = builtin_registry()
    for failure in failures:
        print(f"warning: plugin failed to load: {failure.source}: {failure.error}",
              file=sys.stderr)
    result = load_workflow(path, registry)
    for issue in result.issues:
        print(f"note: {issue}", file=sys.stderr)
    return result


def _cmd_run(args: argparse.Namespace) -> int:
    result = _load(args.workflow)
    graph = result.graph

    for override in args.set:
        try:
            target, raw_value = override.split("=", 1)
            node_id, param = target.split(".", 1)
        except ValueError:
            raise ParamError(f"--set expects NODE.PARAM=VALUE, got {override!r}")
        inst = graph.nodes.get(node_id)
        if inst is None:
            raise ParamError(f"--set: no node with id {node_id!r} "
                             f"(ids: {sorted(graph.nodes)})")
        spec = next((p for p in inst.spec.params if p.name == param), None)
        if spec is None:
            raise ParamError(f"--set: {inst.spec.type_id} has no param {param!r}")
        graph.set_param(node_id, param, spec.parse(raw_value))

    sinks = graph.side_effect_nodes()
    armed = [] if args.no_sinks else sinks
    observed = args.target or sinks
    if not observed and not armed:
        print("error: workflow has no sink nodes; pass --target NODE_ID",
              file=sys.stderr)
        return 2
    unknown = [t for t in args.target if t not in graph.nodes]
    if unknown:
        raise ParamError(f"--target: unknown node id(s) {unknown} "
                         f"(ids: {sorted(graph.nodes)})")

    settings = EngineSettings()
    if args.workers is not None:
        settings.workers = args.workers
    service = ExecutionService(graph, settings,
                               Resources(base_dir=result.base_dir))
    try:
        report = service.run(observed=observed, armed=armed, mode="batch")
    finally:
        service.close()

    if args.profile:
        print(report.to_text())
    else:
        state = "ok" if report.ok else "FAILED"
        print(f"{state}: {len(report.executed())} executed, "
              f"{len(report.cached())} cached, {report.wall_ms:.1f} ms")
    for nid in args.target:
        for port, value in sorted(service.get_output(nid).items()):
            print(f"{nid}.{port}: {summary_of(value)}")
    for err in report.errors:
        print(f"error in {err.node_id}: {err.message}", file=sys.stderr)
    return 0 if report.ok else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    result = _load(args.workflow)
    result.graph.topo_order()  # raises on cycles
    n, e = len(result.graph.nodes), len(result.graph.edges)
    title = result.metadata.get("title", "(untitled)")
    print(f"ok: {title!r} — {n} node(s), {e} edge(s), "
          f"{len(result.issues)} issue(s)")
    return 0 if not result.issues else 1


def _cmd_nodes_list() -> int:
    registry, _ = builtin_registry()
    for category, specs in sorted(registry.categories().items()):
        print(category)
        for spec in specs:
            print(f"  {spec.type_id:<32} {spec.label}  (v{spec.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
