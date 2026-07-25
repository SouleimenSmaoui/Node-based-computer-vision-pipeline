"""Invert — photographic negative (255 − value), space-preserving."""

from __future__ import annotations

import cv2

from cvflow.sdk import ImageIn, ImageOut, Node, node


@node(
    id="cvflow.filters.invert",
    version="1.0",
    category="Filtering",
    label="Invert",
    doc="Inverts pixel values (negative); keeps the colour space.",
    keywords=("negative", "complement", "not"),
)
class Invert(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        ctx.outputs.out = img.derive(cv2.bitwise_not(img.data))
