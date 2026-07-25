"""Warp Affine — rotate, scale and translate about a centre."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    ColorSpace,
    EnumParam,
    FloatParam,
    ImageIn,
    ImageOut,
    Node,
    node,
)

_INTERP = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
           "cubic": cv2.INTER_CUBIC}
_BORDERS = {"constant": cv2.BORDER_CONSTANT, "replicate": cv2.BORDER_REPLICATE,
            "reflect": cv2.BORDER_REFLECT_101, "wrap": cv2.BORDER_WRAP}


@node(
    id="cvflow.geometry.warp_affine",
    version="1.0",
    category="Geometry",
    label="Warp Affine",
    doc="Rotation, scaling and translation in one resampling step — use this "
        "for angles that are not multiples of 90 degrees (Rotate / Flip is "
        "lossless and cheaper for those). Output keeps the input size, so a "
        "rotated image is cropped at the corners unless you scale down.",
    keywords=("rotate", "affine", "warp", "scale", "translate", "shift", "align"),
)
class WarpAffine(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    angle = FloatParam("Angle", default=0.0, min=-360.0, max=360.0, decimals=2,
                       tooltip="Degrees, counter-clockwise.")
    scale = FloatParam("Scale", default=1.0, min=0.01, max=10.0, decimals=3)
    tx = FloatParam("Shift X", default=0.0, min=-10000.0, max=10000.0, decimals=1,
                    tooltip="Pixels, applied after the rotation.")
    ty = FloatParam("Shift Y", default=0.0, min=-10000.0, max=10000.0, decimals=1)
    interp = EnumParam("Interpolation", choices=tuple(_INTERP), default="linear")
    border = EnumParam("Border", choices=tuple(_BORDERS), default="constant",
                       tooltip="How to fill pixels pulled in from outside.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        centre = (img.width / 2.0, img.height / 2.0)
        matrix = cv2.getRotationMatrix2D(centre, ctx.params.angle, ctx.params.scale)
        matrix[0, 2] += ctx.params.tx
        matrix[1, 2] += ctx.params.ty
        # Same rule as Resize (CODE_REVIEW §2.8): interpolating a mask invents
        # values outside {0, 255}, so a BINARY input is resampled nearest.
        interp = (cv2.INTER_NEAREST if img.space is ColorSpace.BINARY
                  else _INTERP[ctx.params.interp])
        warped = cv2.warpAffine(img.data, matrix, (img.width, img.height),
                                flags=interp,
                                borderMode=_BORDERS[ctx.params.border])
        ctx.outputs.out = img.derive(warped)
