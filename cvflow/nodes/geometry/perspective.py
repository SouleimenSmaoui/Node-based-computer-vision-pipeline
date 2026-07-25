"""Perspective Warp — rectify a quadrilateral into a rectangle."""

from __future__ import annotations

import cv2
import numpy as np

from cvflow.sdk import (
    ColorSpace,
    EnumParam,
    ImageIn,
    ImageOut,
    IntParam,
    Issue,
    Node,
    PointParam,
    node,
)

_INTERP = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
           "cubic": cv2.INTER_CUBIC}


@node(
    id="cvflow.geometry.perspective",
    version="1.0",
    category="Geometry",
    label="Perspective Warp",
    doc="Maps four source corners onto a rectangle, removing the foreshortening "
        "of a part photographed off-axis. Give the corners in order — top-left, "
        "top-right, bottom-right, bottom-left — as seen in the source image; "
        "getting the order wrong mirrors or twists the result rather than "
        "failing. Measurements taken after this are in output pixels, so set "
        "the output size to a known physical scale if you care about units.",
    keywords=("perspective", "warp", "rectify", "deskew", "quad", "homography",
              "four point"),
)
class PerspectiveWarp(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    top_left = PointParam("Top-left", default=(0, 0))
    top_right = PointParam("Top-right", default=(0, 0))
    bottom_right = PointParam("Bottom-right", default=(0, 0))
    bottom_left = PointParam("Bottom-left", default=(0, 0))
    width = IntParam("Output width", default=0, min=0, max=16384,
                     tooltip="0 = same as the input.")
    height = IntParam("Output height", default=0, min=0, max=16384,
                      tooltip="0 = same as the input.")
    interp = EnumParam("Interpolation", choices=tuple(_INTERP), default="linear")

    def validate(self, params) -> list[Issue]:
        corners = [params[k] for k in
                   ("top_left", "top_right", "bottom_right", "bottom_left")]
        if len({tuple(c) for c in corners}) < 4:
            return [Issue("the four corners must be distinct — set them to the "
                          "quadrilateral you want rectified", level="error")]
        return []

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        p = ctx.params
        src = np.array([p.top_left, p.top_right, p.bottom_right, p.bottom_left],
                       dtype=np.float32)
        out_w = p.width or img.width
        out_h = p.height or img.height
        dst = np.array([(0, 0), (out_w - 1, 0), (out_w - 1, out_h - 1),
                        (0, out_h - 1)], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(src, dst)
        interp = (cv2.INTER_NEAREST if img.space is ColorSpace.BINARY
                  else _INTERP[p.interp])
        warped = cv2.warpPerspective(img.data, matrix, (out_w, out_h), flags=interp)
        ctx.outputs.out = img.derive(warped)
