"""Draw Boxes — bounding rectangles of a contour set."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    BoolParam,
    ColorParam,
    ContoursIn,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    node,
)


@node(
    id="cvflow.draw.draw_boxes",
    version="1.0",
    category="Draw",
    label="Draw Boxes",
    doc="Draws each contour's bounding rectangle over the image. Axis-aligned "
        "by default; the rotated option uses minAreaRect, which is what you "
        "want for measuring an elongated part that is not square to the camera.",
    keywords=("box", "bbox", "rectangle", "bounding", "annotate", "overlay"),
)
class DrawBoxes(Node):
    image = ImageIn("Image")
    contours = ContoursIn("Contours")
    out = ImageOut("Image", space="BGR")

    color = ColorParam("Colour", default=(0, 255, 0))
    thickness = IntParam("Thickness", default=2, min=1, max=32)
    rotated = BoolParam("Rotated boxes", default=False,
                        tooltip="Use the minimum-area rotated rectangle instead "
                                "of the axis-aligned one.")
    index_labels = BoolParam("Number them", default=False,
                             tooltip="Draw each box's index, matching the "
                                     "contour order.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        canvas = img.bgr_canvas()
        colour = tuple(int(c) for c in ctx.params.color)
        thickness = ctx.params.thickness

        for i, contour in enumerate(ctx.inputs.contours.contours):
            if ctx.params.rotated:
                import numpy as np

                box = cv2.boxPoints(cv2.minAreaRect(contour))
                cv2.drawContours(canvas, [np.intp(box)], 0, colour, thickness)
                anchor = tuple(int(v) for v in box.min(axis=0))
            else:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(canvas, (x, y), (x + w, y + h), colour, thickness)
                anchor = (x, y)
            if ctx.params.index_labels:
                cv2.putText(canvas, str(i), (anchor[0], max(12, anchor[1] - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1,
                            cv2.LINE_AA)

        ctx.outputs.out = img.derive(canvas, space="BGR")
