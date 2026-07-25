"""Unsharp Mask — sharpen by subtracting a blurred copy."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    ColorSpace,
    FloatParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    node,
)


@node(
    id="cvflow.filters.unsharp_mask",
    version="1.0",
    category="Filtering",
    label="Unsharp Mask",
    doc="Sharpens via out = src + amount x (src - blur). Amount 0 is a no-op; "
        "large amounts amplify noise and clip highlights, so denoise first. "
        "Radius sets the feature size being enhanced.",
    keywords=("sharpen", "unsharp", "detail", "contrast", "highpass"),
)
class UnsharpMask(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    radius = IntParam("Radius", default=5, min=1, max=99, step=2, odd_only=True,
                      tooltip="Blur kernel size — the scale of detail enhanced.")
    sigma = FloatParam("Sigma", default=0.0, min=0.0, max=50.0, decimals=2,
                       tooltip="0 = derived from the radius.")
    amount = FloatParam("Amount", default=1.0, min=0.0, max=5.0, decimals=2,
                        tooltip="Strength of the enhancement. 0 leaves the "
                                "image unchanged.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        r = ctx.params.radius
        amount = ctx.params.amount
        blurred = cv2.GaussianBlur(img.data, (r, r), ctx.params.sigma)
        # addWeighted saturates for uint8, which is the behaviour we want at
        # the clipping ends rather than wraparound.
        result = cv2.addWeighted(img.data, 1.0 + amount, blurred, -amount, 0.0)
        space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        ctx.outputs.out = img.derive(result, space=space)
