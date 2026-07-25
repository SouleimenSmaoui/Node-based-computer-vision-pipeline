"""Load Image — file source node."""

from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np

from cvflow.sdk import (
    ColorSpace,
    EnumParam,
    ImageBuffer,
    ImageOut,
    Node,
    PathParam,
    node,
    resolve_path,
)

_FILTER = "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"


@node(
    id="cvflow.io.load_image",
    version="1.0",
    category="Input / Output",
    label="Load Image",
    doc="Reads an image file from disk. Paths may be relative to the workflow file.",
    keywords=("read", "open", "file", "source"),
)
class LoadImage(Node):
    image = ImageOut("Image")

    path = PathParam("File", mode="open", filter=_FILTER)
    color = EnumParam("Color", choices=("BGR", "GRAY"), default="BGR",
                      tooltip="Decode as 3-channel BGR or single-channel grayscale")

    def process(self, ctx) -> None:
        raw = ctx.params.path
        ctx.ensure(bool(raw), "no file selected")
        p = resolve_path(ctx.resources.base_dir, raw)
        ctx.ensure(p.is_file(), f"file not found: {p}")
        flags = cv2.IMREAD_COLOR if ctx.params.color == "BGR" else cv2.IMREAD_GRAYSCALE
        # imdecode over a numpy buffer: unicode-safe on Windows (cv2.imread is not).
        data = np.fromfile(str(p), dtype=np.uint8)
        arr = cv2.imdecode(data, flags)
        ctx.ensure(arr is not None, f"could not decode image: {p}")
        space = ColorSpace.BGR if ctx.params.color == "BGR" else ColorSpace.GRAY
        ctx.outputs.image = ImageBuffer(arr, space, meta={"path": str(p)})

    @classmethod
    def external_state(cls, params: dict[str, Any], base_dir: str | None) -> Any:
        """File identity (mtime + size) so on-disk changes invalidate the cache."""
        raw = params.get("path") or ""
        if not raw:
            return "no-file"
        p = resolve_path(base_dir, raw)
        try:
            st = os.stat(p)
            return [st.st_mtime_ns, st.st_size]
        except OSError:
            return f"missing:{p}"
