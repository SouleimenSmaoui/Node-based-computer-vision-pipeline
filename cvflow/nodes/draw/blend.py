"""Blend — mix two images."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import EnumParam, FloatParam, ImageIn, ImageOut, Node, node

_MODES = ("mix", "add", "difference", "multiply", "screen", "lighten", "darken")


@node(
    id="cvflow.draw.blend",
    version="1.0",
    category="Draw",
    label="Blend",
    doc="Combines two images of the same size. 'mix' cross-fades by opacity — "
        "the before/after comparison. 'difference' is the one to reach for "
        "when checking alignment or finding what changed between two frames: "
        "identical inputs give black.",
    keywords=("blend", "mix", "composite", "difference", "compare", "add"),
)
class Blend(Node):
    base = ImageIn("Base")
    top = ImageIn("Top")
    out = ImageOut("Image", space="BGR")

    mode = EnumParam("Mode", choices=_MODES, default="mix")
    opacity = FloatParam("Opacity", default=0.5, min=0.0, max=1.0, decimals=2,
                         tooltip="Weight of the Top image; applies to 'mix' and "
                                 "scales the others' contribution.")

    def process(self, ctx) -> None:
        base_buf, top_buf = ctx.inputs.base, ctx.inputs.top
        ctx.ensure(base_buf.data.shape[:2] == top_buf.data.shape[:2],
                   f"Base is {base_buf.width}x{base_buf.height} but Top is "
                   f"{top_buf.width}x{top_buf.height} — insert a Resize")

        # Promote both to BGR so mixed-space pairs (a mask over a photo) work.
        a = base_buf.bgr_canvas()
        b = top_buf.bgr_canvas()
        alpha = float(ctx.params.opacity)
        mode = ctx.params.mode

        if mode == "mix":
            result = cv2.addWeighted(a, 1.0 - alpha, b, alpha, 0.0)
        elif mode == "add":
            result = cv2.add(a, (b * alpha).astype(np.uint8))
        elif mode == "difference":
            result = cv2.absdiff(a, b)
        elif mode == "multiply":
            result = ((a.astype(np.float32) * b.astype(np.float32)) / 255.0
                      ).astype(np.uint8)
        elif mode == "screen":
            inv = (255.0 - a.astype(np.float32)) * (255.0 - b.astype(np.float32))
            result = (255.0 - inv / 255.0).astype(np.uint8)
        elif mode == "lighten":
            result = cv2.max(a, b)
        else:  # darken
            result = cv2.min(a, b)

        if mode not in ("mix", "add"):
            # Keep opacity meaningful for every mode: fade the effect back
            # toward the base rather than ignoring the slider.
            result = cv2.addWeighted(a, 1.0 - alpha, result, alpha, 0.0)

        ctx.outputs.out = base_buf.derive(result, space="BGR")
