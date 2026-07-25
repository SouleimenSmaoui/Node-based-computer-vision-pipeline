"""Draw Contours — render contours over an image as a BGR result.

Output is always BGR: a grayscale base is promoted so coloured strokes are
visible. (In the GUI you can also drop the geometry output straight onto a
viewer as a crisp vector overlay — this node bakes it into pixels for export.)
"""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    ContoursIn,
    EnumParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    node,
)

_COLORS = {  # BGR
    "green": (0, 255, 0), "red": (0, 0, 255), "blue": (255, 0, 0),
    "yellow": (0, 255, 255), "cyan": (255, 255, 0), "magenta": (255, 0, 255),
    "white": (255, 255, 255),
}


@node(
    id="cvflow.draw.draw_contours",
    version="1.0",
    category="Draw",
    label="Draw Contours",
    doc="Draws contours over the image (thickness −1 fills them).",
    keywords=("overlay", "annotate", "outline"),
)
class DrawContours(Node):
    image = ImageIn("Image")
    contours = ContoursIn("Contours")
    out = ImageOut("Image", space="BGR")

    color = EnumParam("Color", choices=tuple(_COLORS), default="green")
    thickness = IntParam("Thickness", default=2, min=-1, max=20,
                         tooltip="−1 fills each contour")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        canvas = img.bgr_canvas()
        cnts = ctx.inputs.contours
        if cnts is not None and len(cnts):
            cv2.drawContours(canvas, list(cnts.contours), -1,
                             _COLORS[ctx.params.color], ctx.params.thickness)
        ctx.outputs.out = img.derive(canvas, space="BGR")
