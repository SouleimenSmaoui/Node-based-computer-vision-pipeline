"""Filter Contours — keep only the contours inside given shape bands."""

from __future__ import annotations

import cv2

from cvflow.sdk import (
    BoolParam,
    ContourSet,
    ContoursIn,
    ContoursOut,
    Node,
    RangeParam,
    node,
)


@node(
    id="cvflow.analysis.filter_contours",
    version="1.0",
    category="Analysis",
    label="Filter Contours",
    doc="Keeps contours whose area and aspect ratio fall inside the given "
        "bands. This is where a blob pipeline usually becomes reliable: "
        "threshold generously, then reject by shape rather than trying to "
        "find one threshold that isolates the parts perfectly.",
    keywords=("filter", "contour", "blob", "area", "aspect", "reject", "size"),
)
class FilterContours(Node):
    contours = ContoursIn("Contours")
    out = ContoursOut("Contours")

    area = RangeParam("Area band", default=(0.0, 1_000_000.0),
                      min=0.0, max=100_000_000.0, decimals=1,
                      tooltip="Contour area in px^2, inclusive at both ends.")
    aspect = RangeParam("Aspect band", default=(0.0, 100.0),
                        min=0.0, max=1000.0, decimals=2,
                        tooltip="Bounding-box width / height. A square is 1.0; "
                                "use a narrow band to keep only elongated or "
                                "only compact blobs.")
    invert = BoolParam("Invert", default=False,
                       tooltip="Keep exactly the contours that do NOT match — "
                               "useful for inspecting what a filter discards.")

    def process(self, ctx) -> None:
        source: ContourSet = ctx.inputs.contours
        area_lo, area_hi = ctx.params.area
        aspect_lo, aspect_hi = ctx.params.aspect
        invert = ctx.params.invert

        kept = []
        for contour in source.contours:
            area = float(cv2.contourArea(contour))
            _, _, w, h = cv2.boundingRect(contour)
            aspect = (w / h) if h else 0.0
            matches = (area_lo <= area <= area_hi
                       and aspect_lo <= aspect <= aspect_hi)
            if matches != invert:
                kept.append(contour)

        # Dropping contours invalidates hierarchy indices, which refer to
        # positions in the original tuple — same reasoning as Find Contours.
        ctx.outputs.out = ContourSet(tuple(kept), None, ref_size=source.ref_size)
