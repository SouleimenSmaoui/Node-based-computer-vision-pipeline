"""Rotate / Flip — lossless 90-degree rotations and mirroring."""

from __future__ import annotations

import cv2

from cvflow.sdk import EnumParam, ImageIn, ImageOut, Node, node

_ROTATIONS = {
    "90 cw": cv2.ROTATE_90_CLOCKWISE,
    "180": cv2.ROTATE_180,
    "90 ccw": cv2.ROTATE_90_COUNTERCLOCKWISE,
}
_FLIPS = {"horizontal": 1, "vertical": 0, "both": -1}


@node(
    id="cvflow.geometry.rotate_flip",
    version="1.0",
    category="Geometry",
    label="Rotate / Flip",
    doc="Right-angle rotation and mirroring. Nothing is resampled and no "
        "pixel value changes, so masks, labels and measurements survive "
        "exactly — use Warp Affine for arbitrary angles, which must "
        "interpolate. Rotation is applied first, then the flip.",
    keywords=("rotate", "flip", "mirror", "transpose", "orientation", "90"),
)
class RotateFlip(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    rotate = EnumParam("Rotate", choices=("none", "90 cw", "180", "90 ccw"),
                       default="none",
                       tooltip="Applied before the flip.")
    flip = EnumParam("Flip", choices=("none", "horizontal", "vertical", "both"),
                     default="none")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        result = img.data
        if ctx.params.rotate != "none":
            result = cv2.rotate(result, _ROTATIONS[ctx.params.rotate])
        if ctx.params.flip != "none":
            result = cv2.flip(result, _FLIPS[ctx.params.flip])
        if result is img.data:
            # Both set to none: cv2 never ran, so this is still the frozen input
            # array. Copy rather than hand the same buffer out as a new output.
            result = img.writable_copy()
        # Pure rearrangement: every output value was an input value, so a
        # BINARY mask stays a valid BINARY mask.
        ctx.outputs.out = img.derive(result)
