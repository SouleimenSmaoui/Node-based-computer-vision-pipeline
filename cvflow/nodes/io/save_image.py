"""Save Image — side-effect sink. Runs only when armed (docs/01 §6.1):
never on a live parameter tweak, so tuning can't spray files to disk.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from cvflow.sdk import BoolParam, ImageIn, Node, PathParam, node, resolve_path


@node(
    id="cvflow.io.save_image",
    version="1.0",
    category="Input / Output",
    label="Save Image",
    doc="Writes the input image to disk. Format follows the file extension.",
    keywords=("write", "export", "png", "jpg", "sink"),
)
class SaveImage(Node):
    side_effect = True
    cacheable = False

    image = ImageIn("Image")

    path = PathParam("File", mode="save", filter="*.png *.jpg *.bmp *.tif")
    make_dirs = BoolParam("Create folders", default=True,
                          tooltip="Create missing parent directories")

    def process(self, ctx) -> None:
        ctx.ensure(bool(ctx.params.path), "no output file set")
        p = resolve_path(ctx.resources.base_dir, ctx.params.path)
        suffix = p.suffix.lower()
        ctx.ensure(suffix in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"),
                   f"unsupported image extension: {suffix or '(none)'}")
        if ctx.params.make_dirs:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(suffix, ctx.inputs.image.data)
        ctx.ensure(ok, f"encoding failed for {suffix}")
        # tofile: unicode-safe on Windows (cv2.imwrite is not).
        np.asarray(encoded).tofile(str(p))
        ctx.log.info("wrote %s", p)
