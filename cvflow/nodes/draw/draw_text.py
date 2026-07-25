"""Draw Text — burn a caption into the image."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    BoolParam,
    ColorParam,
    FloatParam,
    ImageIn,
    ImageOut,
    IntParam,
    Node,
    PointParam,
    StringParam,
    TextIn,
    node,
)

_FONT = cv2.FONT_HERSHEY_SIMPLEX


@node(
    id="cvflow.draw.draw_text",
    version="1.0",
    category="Draw",
    label="Draw Text",
    doc="Draws a caption at a fixed position. Connect the Text input to show a "
        "measured value instead of the static parameter — the port wins when "
        "it is wired. The position is the text's bottom-left corner, as in "
        "OpenCV; the optional backing plate keeps it readable over busy images.",
    keywords=("text", "label", "caption", "annotate", "overlay", "putText"),
)
class DrawText(Node):
    image = ImageIn("Image")
    text_in = TextIn("Text", optional=True)
    out = ImageOut("Image", space="BGR")

    text = StringParam("Text", default="",
                       tooltip="Ignored when the Text input is connected.")
    position = PointParam("Position", default=(10, 30),
                          tooltip="Bottom-left corner of the text, in pixels.")
    scale = FloatParam("Font scale", default=0.7, min=0.1, max=10.0, decimals=2)
    color = ColorParam("Colour", default=(0, 255, 0))
    thickness = IntParam("Thickness", default=2, min=1, max=16)
    backing = BoolParam("Backing plate", default=False,
                        tooltip="Draw a filled dark box behind the text.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        canvas = img.bgr_canvas()
        supplied = ctx.inputs.text_in
        caption = str(supplied) if supplied is not None else ctx.params.text
        x, y = (int(v) for v in ctx.params.position)
        colour = tuple(int(c) for c in ctx.params.color)
        scale, thickness = ctx.params.scale, ctx.params.thickness

        if caption:
            if ctx.params.backing:
                (tw, th), baseline = cv2.getTextSize(caption, _FONT, scale, thickness)
                cv2.rectangle(canvas, (x - 3, y - th - 3),
                              (x + tw + 3, y + baseline + 3), (0, 0, 0), -1)
            cv2.putText(canvas, caption, (x, y), _FONT, scale, colour,
                        thickness, cv2.LINE_AA)

        ctx.outputs.out = img.derive(canvas, space="BGR")
