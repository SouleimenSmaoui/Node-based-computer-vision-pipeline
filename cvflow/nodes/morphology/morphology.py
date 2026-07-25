"""Morphology — erode / dilate / open / close / gradient / tophat / blackhat.

Works on any image (applied channel-wise), so the port is unconstrained and the
output keeps the input's colour space.
"""

from __future__ import annotations

import cv2

from cvflow.sdk import EnumParam, ImageIn, ImageOut, IntParam, Node, node

_OPS = {
    "erode": None, "dilate": None,
    "open": cv2.MORPH_OPEN, "close": cv2.MORPH_CLOSE,
    "gradient": cv2.MORPH_GRADIENT, "tophat": cv2.MORPH_TOPHAT,
    "blackhat": cv2.MORPH_BLACKHAT,
}
_SHAPES = {"rect": cv2.MORPH_RECT, "ellipse": cv2.MORPH_ELLIPSE, "cross": cv2.MORPH_CROSS}


@node(
    id="cvflow.morphology.morphology",
    version="1.0",
    category="Morphology",
    label="Morphology",
    doc="Morphological operations with a configurable structuring element.",
    keywords=("erode", "dilate", "open", "close", "gradient"),
)
class Morphology(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    op = EnumParam("Operation", choices=tuple(_OPS), default="dilate")
    shape = EnumParam("Kernel shape", choices=tuple(_SHAPES), default="ellipse")
    ksize = IntParam("Kernel size", default=3, min=1, max=99, step=2, odd_only=True)
    iterations = IntParam("Iterations", default=1, min=1, max=20)

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        k = ctx.params.ksize
        kernel = cv2.getStructuringElement(_SHAPES[ctx.params.shape], (k, k))
        op = ctx.params.op
        if op == "erode":
            out = cv2.erode(img.data, kernel, iterations=ctx.params.iterations)
        elif op == "dilate":
            out = cv2.dilate(img.data, kernel, iterations=ctx.params.iterations)
        else:
            out = cv2.morphologyEx(img.data, _OPS[op], kernel,
                                   iterations=ctx.params.iterations)
        ctx.outputs.out = img.derive(out)
