"""Node type registry (docs/01 §4): type id → versions → NodeSpec."""

from __future__ import annotations

from typing import Iterable

from cvflow.core.errors import UnknownNodeTypeError
from cvflow.core.node import Node, NodeSpec


def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


class NodeRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, dict[str, NodeSpec]] = {}

    def register(self, node_class: type[Node]) -> NodeSpec:
        spec = node_class.__cvflow_spec__
        if spec is None or spec.node_class is not node_class:
            raise ValueError(
                f"{node_class.__name__} is not decorated with @node"
            )
        versions = self._specs.setdefault(spec.type_id, {})
        if spec.version in versions and versions[spec.version].node_class is not node_class:
            raise ValueError(
                f"duplicate registration for {spec.type_id}@{spec.version}"
            )
        versions[spec.version] = spec
        return spec

    def get(self, type_id: str, version: str | None = None) -> NodeSpec:
        versions = self._specs.get(type_id)
        if not versions:
            raise UnknownNodeTypeError(
                f"unknown node type {type_id!r} — is its plugin installed?"
            )
        if version is None:
            return versions[max(versions, key=_version_key)]
        if version in versions:
            return versions[version]
        # Version drift: hand back the latest; the caller runs migrate_params.
        return versions[max(versions, key=_version_key)]

    def has(self, type_id: str) -> bool:
        return type_id in self._specs

    def all_specs(self) -> list[NodeSpec]:
        return [self.get(type_id) for type_id in sorted(self._specs)]

    def categories(self) -> dict[str, list[NodeSpec]]:
        out: dict[str, list[NodeSpec]] = {}
        for spec in self.all_specs():
            out.setdefault(spec.category, []).append(spec)
        return out

    def search(self, text: str) -> list[NodeSpec]:
        needle = text.lower()
        hits = []
        for spec in self.all_specs():
            haystack = " ".join(
                (spec.label, spec.type_id, spec.category, *spec.keywords)
            ).lower()
            if needle in haystack:
                hits.append(spec)
        return hits

    def register_all(self, node_classes: Iterable[type[Node]]) -> None:
        for cls in node_classes:
            self.register(cls)
