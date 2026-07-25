"""Resize — scale by factor or to absolute dimensions."""

from __future__ import annotations

import cv2

from cvflow.sdk import EnumParam, FloatParam, ImageIn, ImageOut, IntParam, Node, node

_INTERP = {
    "nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
    "cubic": cv2.INTER_CUBIC, "area": cv2.INTER_AREA,
}


@node(
    id="cvflow.geometry.resize",
    version="1.0",
    category="Geometry",
    label="Resize",
    doc="Resize an image by a scale factor or to explicit width/height.",
    keywords=("scale", "resample", "downscale", "upscale"),
)
class Resize(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    mode = EnumParam("Mode", choices=("scale", "absolute"), default="scale")
    scale = FloatParam("Scale", default=0.5, min=0.05, max=8.0, decimals=3)
    width = IntParam("Width", default=640, min=1, max=16384)
    height = IntParam("Height", default=480, min=1, max=16384)
    interp = EnumParam("Interpolation", choices=tuple(_INTERP), default="area")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        interp = _INTERP[ctx.params.interp]
        if ctx.params.mode == "absolute":
            out = cv2.resize(img.data, (ctx.params.width, ctx.params.height),
                             interpolation=interp)
        else:
            s = ctx.params.scale
            out = cv2.resize(img.data, None, fx=s, fy=s, interpolation=interp)
        ctx.outputs.out = img.derive(out)
