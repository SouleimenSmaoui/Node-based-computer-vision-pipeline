"""Crop ROI — cut a rectangular region out of an image."""

from __future__ import annotations

from cvflow.sdk import BoolParam, ImageIn, ImageOut, Node, RectParam, node


@node(
    id="cvflow.geometry.crop_roi",
    version="1.0",
    category="Geometry",
    label="Crop ROI",
    doc="Crops to a rectangle in image pixels. Cropping early is the cheapest "
        "speed-up available — every downstream node then works on fewer "
        "pixels. A rectangle reaching outside the image is clipped to it "
        "rather than erroring, so a fixed ROI keeps working when the input "
        "size changes.",
    keywords=("crop", "roi", "region", "cut", "trim", "window"),
)
class CropRoi(Node):
    image = ImageIn("Image")
    out = ImageOut("Image", same_space_as="image")

    rect = RectParam("Region",
                     tooltip="x, y, width, height in pixels. Width or height 0 "
                             "means 'the rest of the image' from x, y.")
    copy = BoolParam("Copy pixels", default=False,
                     tooltip="Off shares memory with the input (cheap). On "
                             "makes a compact copy, which is worth it when "
                             "cropping a small ROI out of a very large image.")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        x, y, w, h = ctx.params.rect
        # 0 extent means 'to the far edge' — the natural reading of an unset
        # width, and it keeps the default rect (0,0,0,0) a pass-through rather
        # than a node that silently emits nothing.
        if w <= 0:
            w = img.width - x
        if h <= 0:
            h = img.height - y
        x, y, w, h = RectParam.clip_to((x, y, w, h), img.width, img.height)
        ctx.ensure(w > 0 and h > 0,
                   f"region {tuple(ctx.params.rect)} lies outside the "
                   f"{img.width}x{img.height} image")

        view = img.data[y:y + h, x:x + w]
        ctx.outputs.out = img.derive(view.copy() if ctx.params.copy else view)
