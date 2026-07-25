"""Find Contours — extract contours from a binary/grayscale image.

Input is Image[GRAY]; a BINARY mask (from Threshold/Canny) satisfies it via the
BINARY→GRAY subtype rule, so a threshold output wires straight in.
"""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    ContourSet,
    ContoursOut,
    EnumParam,
    FloatParam,
    ImageIn,
    Node,
    node,
)

_MODES = {"external": cv2.RETR_EXTERNAL, "list": cv2.RETR_LIST,
          "ccomp": cv2.RETR_CCOMP, "tree": cv2.RETR_TREE}
_METHODS = {"simple": cv2.CHAIN_APPROX_SIMPLE, "none": cv2.CHAIN_APPROX_NONE}


@node(
    id="cvflow.analysis.find_contours",
    version="1.0",
    category="Analysis",
    label="Find Contours",
    doc="Finds contours in a binary image; optionally drops tiny ones by area.",
    keywords=("contour", "blob", "shape", "segment"),
)
class FindContours(Node):
    image = ImageIn("Image", space="GRAY")
    contours = ContoursOut("Contours")

    mode = EnumParam("Retrieval", choices=tuple(_MODES), default="external")
    method = EnumParam("Approximation", choices=tuple(_METHODS), default="simple")
    min_area = FloatParam("Min area", default=0.0, min=0.0, max=1_000_000.0, decimals=1,
                          tooltip="Discard contours smaller than this (px²)")

    def process(self, ctx) -> None:
        img = ctx.inputs.image
        # findContours can scribble on its input on some builds → give it a copy.
        found, hierarchy = cv2.findContours(
            img.writable_copy(), _MODES[ctx.params.mode], _METHODS[ctx.params.method])
        min_area = ctx.params.min_area
        if min_area > 0 and found:
            keep = [c for c in found if cv2.contourArea(c) >= min_area]
            found = keep
            hierarchy = None  # filtering invalidates the original hierarchy indices
        ctx.outputs.contours = ContourSet(
            tuple(found), hierarchy, ref_size=(img.width, img.height))
