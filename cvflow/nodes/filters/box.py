"""Box Blur — unweighted mean over a square neighbourhood; the cheapest blur."""

from __future__ import annotations

import cv2

from cvflow.sdk import ColorSpace, ImageIn, ImageOut, IntParam, Node, node


@node(
    id="cvflow.filters.box_blur",
    version="1.0",
    category="Filtering",
    label="Box Blur",
    doc="Averages a square neighbourhood with equal weights. Faster than a "
        "Gaussian and fine for previews or background estimation, but its "
        "sharp kernel edge causes ringing on high-contrast detail.",
    keywords=("box", "mean", "average", "smooth", "lowpass", "fast"),
)
class BoxBlur(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    kernel = IntParam("Kernel size", default=5, min=1, max=99, step=2, odd_only=True,
                      tooltip="Neighbourhood side length in pixels.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        k = ctx.params.kernel
        blurred = cv2.blur(img.data, (k, k))
        # Averaging produces in-between values, so a BINARY input stops being
        # {0, 255}. Emit GRAY rather than mislabel it (nodes/README.md).
        space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        ctx.outputs.out = img.derive(blurred, space=space)
