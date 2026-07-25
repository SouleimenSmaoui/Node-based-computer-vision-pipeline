"""Testing harness for node authors (docs/04 §8).

``run_node`` builds a real ExecutionContext (validation, freezing, and error
mapping included), so a passing test means the node behaves inside the engine
— without instantiating an engine or a graph.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from cvflow.core.node import Node
from cvflow.core.params import validate_params
from cvflow.core.types.image import ColorSpace, ImageBuffer
from cvflow.engine.context import ExecutionContext, Resources


def run_node(
    node_cls: type[Node],
    *,
    inputs: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    resources: Resources | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = node_cls.__cvflow_spec__
    if spec is None:
        raise TypeError(f"{node_cls.__name__} is not decorated with @node")
    values = validate_params(spec.params, dict(params or {}))
    # The engine hands every declared input to the node, using None for ports
    # with no incoming edge (executor._assemble_inputs). Mirror that here, or a
    # node with an optional port would see AttributeError under test and None
    # in production — the harness has to be faithful to be worth anything.
    supplied = dict(inputs or {})
    assembled = {decl.name: supplied.pop(decl.name, None) for decl in spec.inputs}
    if supplied:
        raise TypeError(
            f"{node_cls.__name__} has no input port(s) {sorted(supplied)} "
            f"(declared: {[d.name for d in spec.inputs]})")
    ctx = ExecutionContext(
        node_id="test", spec=spec, inputs=assembled, params=values,
        resources=resources or Resources(), state=state)
    obj = node_cls()
    obj.setup(ctx)
    try:
        obj.process(ctx)
        return ctx.outputs.collect()
    finally:
        obj.teardown(ctx)


# ---- synthetic images ------------------------------------------------------


def checker_image(size: int = 64, *, cell: int = 8, space: str = "GRAY") -> ImageBuffer:
    y, x = np.mgrid[0:size, 0:size]
    board = (((x // cell) + (y // cell)) % 2 * 255).astype(np.uint8)
    return _in_space(board, space)


def gradient_image(size: int = 64, *, space: str = "GRAY") -> ImageBuffer:
    row = np.linspace(0, 255, size, dtype=np.uint8)
    return _in_space(np.tile(row, (size, 1)), space)


def blank_image(size: int = 64, *, value: int = 0, space: str = "GRAY") -> ImageBuffer:
    return _in_space(np.full((size, size), value, dtype=np.uint8), space)


def shapes_image(size: int = 128, *, space: str = "BGR") -> ImageBuffer:
    """A rectangle and a circle on black — enough structure for edges/contours."""
    import cv2

    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    q = size // 4
    cv2.rectangle(canvas, (q // 2, q // 2), (2 * q, 2 * q), (40, 200, 240), -1)
    cv2.circle(canvas, (3 * q, 3 * q), q // 2 + 4, (220, 120, 50), -1)
    return _in_space(canvas, space)


def _in_space(gray_or_bgr: np.ndarray, space: str) -> ImageBuffer:
    target = ColorSpace(space)
    arr = gray_or_bgr
    if target.channels == 3 and arr.ndim == 2:
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    elif target.channels == 1 and arr.ndim == 3:
        arr = arr.mean(axis=2).astype(np.uint8)
    return ImageBuffer(np.ascontiguousarray(arr), target)
