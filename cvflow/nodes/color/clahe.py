"""CLAHE — contrast limited adaptive histogram equalization."""

from __future__ import annotations

import cv2
import numpy as np

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
    id="cvflow.color.clahe",
    version="1.0",
    category="Color",
    label="CLAHE",
    doc="Equalizes contrast per tile rather than globally, so detail survives "
        "in both bright and dark regions of an unevenly lit part. The clip "
        "limit caps how far a flat region may be stretched, which is what "
        "stops plain adaptive equalization from turning noise into texture.",
    keywords=("clahe", "contrast", "equalize", "histogram", "adaptive", "lighting"),
)
class Clahe(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    clip = FloatParam("Clip limit", default=2.0, min=0.1, max=40.0, decimals=1,
                      tooltip="Higher gives more contrast and more amplified "
                              "noise in flat areas.")
    tiles = IntParam("Tile grid", default=8, min=1, max=64,
                     tooltip="Image is divided into this many tiles per axis. "
                             "1 makes it plain global equalization.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        ctx.ensure(img.data.dtype == np.uint8,
                   f"CLAHE needs an 8-bit image, got {img.data.dtype}")
        t = ctx.params.tiles
        clahe = cv2.createCLAHE(clipLimit=ctx.params.clip, tileGridSize=(t, t))

        if img.channels == 1:
            result = clahe.apply(img.data)
            # Equalizing a two-valued mask yields neither a mask nor anything
            # meaningful, but it is at least honestly GRAY afterwards.
            space = ColorSpace.GRAY if img.space is ColorSpace.BINARY else None
        else:
            ctx.ensure(img.space is ColorSpace.BGR,
                       f"CLAHE handles GRAY or BGR; convert {img.space.value} "
                       f"first (equalizing its channels directly would distort "
                       f"the colour)")
            # Equalize lightness only, in LAB — doing it per BGR channel shifts
            # hue, because each channel gets a different transfer curve.
            lab = cv2.cvtColor(img.data, cv2.COLOR_BGR2LAB)
            lightness, a, b = cv2.split(lab)
            merged = cv2.merge([clahe.apply(lightness), a, b])
            result = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
            space = None

        ctx.outputs.out = img.derive(result, space=space)
