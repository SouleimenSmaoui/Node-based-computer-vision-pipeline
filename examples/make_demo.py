"""Regenerates the demo assets and workflow in this folder.

Also serves as the reference for building graphs programmatically (the same
API the GUI will drive). Run:  python examples/make_demo.py
"""

from __future__ import annotations

from pathlib import Path

import cv2

from cvflow.core.graph import Graph
from cvflow.io.workflow_json import save_workflow
from cvflow.plugins import builtin_registry
from cvflow.sdk.testing import shapes_image

HERE = Path(__file__).parent


def main() -> None:
    assets = HERE / "assets"
    assets.mkdir(exist_ok=True)
    sample = shapes_image(480)
    cv2.imwrite(str(assets / "sample.png"), sample.data)

    registry, _ = builtin_registry()
    g = Graph()
    g.add_node(registry.get("cvflow.io.load_image"), node_id="load",
               params={"path": "../assets/sample.png"}, pos=(-460, 0))
    g.add_node(registry.get("cvflow.color.to_gray"), node_id="gray", pos=(-230, 0))
    g.add_node(registry.get("cvflow.filters.gaussian_blur"), node_id="blur",
               params={"kernel": 5, "sigma": 1.2}, pos=(0, 0))
    g.add_node(registry.get("cvflow.edges.canny"), node_id="canny",
               params={"low": 60, "high": 160}, pos=(230, 0))
    g.add_node(registry.get("cvflow.io.save_image"), node_id="save",
               params={"path": "../out/edges.png"}, pos=(460, 0))

    g.connect("load", "image", "gray", "image")
    g.connect("gray", "out", "blur", "image")
    g.connect("blur", "out", "canny", "image")
    g.connect("canny", "edges", "save", "image")

    workflows = HERE / "workflows"
    save_workflow(g, workflows / "edges_demo.cvflow.json",
                  metadata={"title": "Edge detection demo",
                            "description": "load → gray → blur → canny → save"})
    print(f"wrote {assets / 'sample.png'}")
    print(f"wrote {workflows / 'edges_demo.cvflow.json'}")


if __name__ == "__main__":
    main()
