"""Overlay Mask — tint an image through a binary mask."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import (
    BoolParam,
    ColorParam,
    FloatParam,
    ImageIn,
    ImageOut,
    Node,
    node,
)


@node(
    id="cvflow.draw.overlay_mask",
    version="1.0",
    category="Draw",
    label="Overlay Mask",
    doc="Tints the masked region over the image, the standard way to check a "
        "segmentation by eye: at partial opacity you can see both what was "
        "selected and the detail underneath, which a hard mask hides.",
    keywords=("overlay", "mask", "tint", "highlight", "segmentation", "alpha"),
)
class OverlayMask(Node):
    image = ImageIn("Image")
    mask = ImageIn("Mask", space="GRAY")
    out = ImageOut("Image", space="BGR")

    color = ColorParam("Colour", default=(0, 0, 255))
    opacity = FloatParam("Opacity", default=0.5, min=0.0, max=1.0, decimals=2,
                         tooltip="1.0 paints the mask solid; 0.0 shows nothing.")
    outline = BoolParam("Outline", default=False,
                        tooltip="Also stroke the mask boundary at full opacity, "
                                "which stays visible at low tint levels.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        mask = ctx.inputs.mask
        ctx.ensure(mask.data.shape[:2] == img.data.shape[:2],
                   f"mask is {mask.width}x{mask.height} but image is "
                   f"{img.width}x{img.height}")

        canvas = img.bgr_canvas()
        colour = tuple(int(c) for c in ctx.params.color)
        selected = mask.data > 0

        if selected.any() and ctx.params.opacity > 0:
            tint = np.empty_like(canvas)
            tint[:] = colour
            alpha = float(ctx.params.opacity)
            blended = cv2.addWeighted(canvas, 1.0 - alpha, tint, alpha, 0.0)
            # Only the selected pixels change; np.where keeps this one vectorised
            # pass rather than a per-pixel loop.
            canvas = np.where(selected[:, :, None], blended, canvas)

        if ctx.params.outline:
            found, _ = cv2.findContours(mask.writable_copy(), cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(canvas, list(found), -1, colour, 2)

        ctx.outputs.out = img.derive(np.ascontiguousarray(canvas), space="BGR")
