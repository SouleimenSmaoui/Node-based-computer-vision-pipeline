"""Color conversions. Phase 0 ships To Gray; the general Convert Color node
joins it in the MVP node sweep (STATUS.md).
"""

from __future__ import annotations

import cv2

from cvflow.sdk import ColorSpace, ImageIn, ImageOut, Node, node

_TO_GRAY = {
    ColorSpace.BGR: cv2.COLOR_BGR2GRAY,
    ColorSpace.RGB: cv2.COLOR_RGB2GRAY,
    ColorSpace.BGRA: cv2.COLOR_BGRA2GRAY,
}


@node(
    id="cvflow.color.to_gray",
    version="1.0",
    category="Color",
    label="To Gray",
    doc="Converts a color image to single-channel grayscale.",
    keywords=("grayscale", "luminance", "convert", "mono"),
)
class ToGray(Node):
    image = ImageIn("Image")
    out = ImageOut("Gray", space="GRAY")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        if img.space in (ColorSpace.GRAY, ColorSpace.BINARY):
            ctx.outputs.out = img.derive(img.data, space="GRAY")
            return
        code = _TO_GRAY.get(img.space)
        ctx.ensure(code is not None,
                   f"cannot convert {img.space.value} directly to GRAY — "
                   f"convert to BGR first")
        ctx.outputs.out = img.derive(cv2.cvtColor(img.data, code), space="GRAY")
