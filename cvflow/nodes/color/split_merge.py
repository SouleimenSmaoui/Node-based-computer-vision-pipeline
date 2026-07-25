"""Split / Merge Channels — take a colour image apart and put it back together.

Splitting is how you get at a single informative channel (saturation for a
colour part, the a* axis for red-vs-green) and run the rest of the pipeline on
one cheap plane instead of three.
"""

from __future__ import annotations

import cv2

from cvflow.sdk import EnumParam, ImageIn, ImageOut, Node, node

_MERGE_SPACES = ("BGR", "HSV", "LAB", "RGB")


@node(
    id="cvflow.color.split_channels",
    version="1.0",
    category="Color",
    label="Split Channels",
    doc="Splits a 3-channel image into three single-channel images. Channel "
        "meaning depends on the input space: B,G,R for BGR; H,S,V for HSV; "
        "L,a,b for LAB. Each output is GRAY, so any grayscale node accepts it.",
    keywords=("split", "channel", "extract", "plane", "band", "hsv", "lab"),
)
class SplitChannels(Node):
    image = ImageIn("Image")
    c1 = ImageOut("Channel 1", space="GRAY")
    c2 = ImageOut("Channel 2", space="GRAY")
    c3 = ImageOut("Channel 3", space="GRAY")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        ctx.ensure(img.channels == 3,
                   f"Split Channels needs a 3-channel image, got {img.channels} "
                   f"({img.space.value})")
        first, second, third = cv2.split(img.data)
        # Each plane is only meaningful as intensity now — the parent space's
        # label would be a lie on a single channel.
        ctx.outputs.c1 = img.derive(first, space="GRAY")
        ctx.outputs.c2 = img.derive(second, space="GRAY")
        ctx.outputs.c3 = img.derive(third, space="GRAY")


@node(
    id="cvflow.color.merge_channels",
    version="1.0",
    category="Color",
    label="Merge Channels",
    doc="Combines three single-channel images into one 3-channel image. The "
        "space setting declares what the channels *mean* — it does not convert "
        "them, so pick the space they actually came from.",
    keywords=("merge", "combine", "channel", "join", "stack"),
)
class MergeChannels(Node):
    c1 = ImageIn("Channel 1", space="GRAY")
    c2 = ImageIn("Channel 2", space="GRAY")
    c3 = ImageIn("Channel 3", space="GRAY")
    out = ImageOut("Image")

    space = EnumParam("Interpret as", choices=_MERGE_SPACES, default="BGR",
                      tooltip="Declares the meaning of the three channels. "
                              "No conversion happens — use To Gray / a convert "
                              "node if you need one.")

    def process(self, ctx) -> None:
        planes = [ctx.inputs.c1, ctx.inputs.c2, ctx.inputs.c3]
        first = planes[0]
        for i, plane in enumerate(planes[1:], start=2):
            ctx.ensure(plane.data.shape[:2] == first.data.shape[:2],
                       f"channel {i} is {plane.width}x{plane.height}, "
                       f"channel 1 is {first.width}x{first.height}")
            ctx.ensure(plane.data.dtype == first.data.dtype,
                       f"channel {i} is {plane.data.dtype}, "
                       f"channel 1 is {first.data.dtype}")
        merged = cv2.merge([p.data for p in planes])
        ctx.outputs.out = first.derive(merged, space=ctx.params.space)
