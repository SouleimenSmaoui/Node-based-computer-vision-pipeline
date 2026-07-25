"""Shared fixtures and tiny test nodes for engine tests.

The Counting* nodes track process() invocations so tests can assert the
engine's incremental behavior (what executed vs what came from cache).
"""

from __future__ import annotations

import numpy as np
import pytest

from cvflow.core.graph import Graph
from cvflow.core.registry import NodeRegistry
from cvflow.sdk import (
    ImageBuffer,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    NumberOut,
    node,
)


@node(id="test.source", category="Test", label="Source")
class SourceNode(Node):
    """Emits a deterministic gray image derived from ``seed``."""

    out = ImageOut("Image", space="GRAY")
    seed = IntParam("Seed", default=1, min=0, max=10_000)
    size = IntParam("Size", default=32, min=2, max=512)

    calls = 0

    def process(self, ctx) -> None:
        type(self).calls += 1
        rng = np.random.default_rng(ctx.params.seed)
        arr = rng.integers(0, 255, (ctx.params.size, ctx.params.size), dtype=np.uint8)
        ctx.outputs.out = ImageBuffer(arr, "GRAY")


@node(id="test.add", category="Test", label="Add")
class AddNode(Node):
    """Adds ``amount`` to the image (saturating)."""

    image = ImageIn("Image", space="GRAY")
    out = ImageOut("Image", space="GRAY")
    amount = IntParam("Amount", default=10, min=0, max=255)

    calls = 0

    def process(self, ctx) -> None:
        type(self).calls += 1
        img = ctx.inputs.image
        import cv2

        result = cv2.add(img.data, ctx.params.amount)
        ctx.outputs.out = img.derive(result)


@node(id="test.mean", category="Test", label="Mean")
class MeanNode(Node):
    image = ImageIn("Image")
    value = NumberOut("Mean")

    calls = 0

    def process(self, ctx) -> None:
        type(self).calls += 1
        ctx.outputs.value = float(ctx.inputs.image.data.mean())


@node(id="test.fail", category="Test", label="Fail")
class FailNode(Node):
    image = ImageIn("Image")
    out = ImageOut("Image")

    def process(self, ctx) -> None:
        raise RuntimeError("intentional test failure")


@pytest.fixture(autouse=True)
def _reset_counters():
    for cls in (SourceNode, AddNode, MeanNode):
        cls.calls = 0
    yield


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    reg.register_all([SourceNode, AddNode, MeanNode, FailNode])
    return reg


@pytest.fixture
def chain_graph(registry) -> Graph:
    """source -> add1 -> add2, plus mean watching add1 (a side branch)."""
    g = Graph()
    g.add_node(registry.get("test.source"), node_id="src")
    g.add_node(registry.get("test.add"), node_id="add1")
    g.add_node(registry.get("test.add"), node_id="add2")
    g.add_node(registry.get("test.mean"), node_id="mean")
    g.connect("src", "out", "add1", "image")
    g.connect("add1", "out", "add2", "image")
    g.connect("add1", "out", "mean", "image")
    return g
