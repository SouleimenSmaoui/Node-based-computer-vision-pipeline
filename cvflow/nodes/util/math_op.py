"""Math Op — arithmetic between two images, or an image and a constant."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import (
    ColorSpace,
    EnumParam,
    FloatParam,
    ImageIn,
    ImageOut,
    Node,
    node,
)

_OPS = ("add", "subtract", "absdiff", "multiply", "divide", "min", "max",
        "and", "or", "xor")


@node(
    id="cvflow.util.math_op",
    version="1.0",
    category="Misc",
    label="Math Op",
    doc="Pixel arithmetic. With both inputs wired it operates image-to-image; "
        "with only the first, it applies the constant instead — so the same "
        "node covers 'subtract the background frame' and 'add 20 to "
        "everything'. Results saturate rather than wrap, so a subtraction "
        "cannot roll 0 round to 255. The bitwise ops are the mask-combining "
        "ones: and/or/xor to intersect, union, or exclusive-or two masks.",
    keywords=("math", "add", "subtract", "difference", "multiply", "divide",
              "and", "or", "xor", "mask", "background"),
)
class MathOp(Node):
    a = ImageIn("A")
    b = ImageIn("B", optional=True)
    out = ImageOut("Image", same_space_as="a")

    op = EnumParam("Operation", choices=_OPS, default="subtract")
    constant = FloatParam("Constant", default=0.0, min=-255.0, max=255.0,
                          decimals=2,
                          tooltip="Used when input B is not connected.")

    def process(self, ctx) -> None:
        first = ctx.inputs.a
        second = ctx.inputs.b
        op = ctx.params.op

        if second is not None:
            ctx.ensure(second.data.shape == first.data.shape,
                       f"A is {first.data.shape} but B is {second.data.shape} — "
                       f"they must match (insert a Resize, or convert spaces)")
            operand = second.data
        else:
            ctx.ensure(op not in ("and", "or", "xor"),
                       f"'{op}' needs both inputs connected")
            value = float(ctx.params.constant)
            # cv2's saturating ops work on magnitudes, and an unsigned operand
            # array cannot hold a negative — so fold the sign into the op.
            if value < 0 and op in ("add", "subtract"):
                op = "subtract" if op == "add" else "add"
                value = -value
            if np.issubdtype(first.data.dtype, np.unsignedinteger):
                value = max(0.0, value)
            operand = np.full_like(first.data, value)

        result = _apply(op, first.data, operand)
        # Arithmetic breaks the {0,255} promise except for the bitwise ops,
        # which can only ever return values already present in their inputs.
        space = (ColorSpace.GRAY
                 if first.space is ColorSpace.BINARY
                 and op not in ("and", "or", "xor", "min", "max")
                 else None)
        ctx.outputs.out = first.derive(result, space=space)


def _apply(op: str, a: np.ndarray, b) -> np.ndarray:
    if op == "add":
        return cv2.add(a, b)
    if op == "subtract":
        return cv2.subtract(a, b)
    if op == "absdiff":
        return cv2.absdiff(a, b)
    if op == "multiply":
        return cv2.multiply(a, b)
    if op == "divide":
        return cv2.divide(a, b)
    if op == "min":
        return cv2.min(a, b)
    if op == "max":
        return cv2.max(a, b)
    if op == "and":
        return cv2.bitwise_and(a, b)
    if op == "or":
        return cv2.bitwise_or(a, b)
    return cv2.bitwise_xor(a, b)
