"""End-to-end CLI: the headless path a CI job or script would use."""

import cv2
import numpy as np
import pytest

from cvflow.cli.main import main
from cvflow.core.graph import Graph
from cvflow.io.workflow_json import save_workflow
from cvflow.plugins import builtin_registry
from cvflow.sdk.testing import shapes_image


@pytest.fixture
def demo_workflow(tmp_path):
    """load -> gray -> blur -> canny -> save, with a real png on disk."""
    assets = tmp_path / "assets"
    assets.mkdir()
    cv2.imwrite(str(assets / "in.png"), np.asarray(shapes_image(96).data))

    registry, _ = builtin_registry()
    g = Graph()
    g.add_node(registry.get("cvflow.io.load_image"), node_id="load",
               params={"path": "assets/in.png"})
    g.add_node(registry.get("cvflow.color.to_gray"), node_id="gray")
    g.add_node(registry.get("cvflow.filters.gaussian_blur"), node_id="blur")
    g.add_node(registry.get("cvflow.edges.canny"), node_id="canny")
    g.add_node(registry.get("cvflow.io.save_image"), node_id="save",
               params={"path": "out/edges.png"})
    g.connect("load", "image", "gray", "image")
    g.connect("gray", "out", "blur", "image")
    g.connect("blur", "out", "canny", "image")
    g.connect("canny", "edges", "save", "image")

    wf = tmp_path / "wf.cvflow.json"
    save_workflow(g, wf, metadata={"title": "cli test"})
    return wf


class TestCli:
    def test_run_writes_output(self, demo_workflow, capsys):
        code = main(["run", str(demo_workflow), "--profile"])
        assert code == 0
        assert (demo_workflow.parent / "out" / "edges.png").exists()
        out = capsys.readouterr().out
        assert "canny" in out and "ok" in out

    def test_run_with_param_override(self, demo_workflow):
        code = main(["run", str(demo_workflow),
                     "--set", "blur.kernel=9", "--set", "canny.low=80"])
        assert code == 0

    def test_tuple_param_override(self, tmp_path, capsys):
        """`--set node.rect=x,y,w,h` — the tuple specs must be reachable from
        the CLI, not just the inspector."""
        cv2.imwrite(str(tmp_path / "in.png"), np.asarray(shapes_image(96).data))
        registry, _ = builtin_registry()
        g = Graph()
        g.add_node(registry.get("cvflow.io.load_image"), node_id="load",
                   params={"path": "in.png"})
        g.add_node(registry.get("cvflow.geometry.crop_roi"), node_id="crop")
        g.connect("load", "image", "crop", "image")
        wf = tmp_path / "crop.cvflow.json"
        save_workflow(g, wf)

        code = main(["run", str(wf), "--target", "crop",
                     "--set", "crop.rect=8,8,32,24"])
        assert code == 0
        assert "32×24" in capsys.readouterr().out

    def test_bad_tuple_override_is_friendly(self, tmp_path, capsys):
        cv2.imwrite(str(tmp_path / "in.png"), np.asarray(shapes_image(32).data))
        registry, _ = builtin_registry()
        g = Graph()
        g.add_node(registry.get("cvflow.io.load_image"), node_id="load",
                   params={"path": "in.png"})
        g.add_node(registry.get("cvflow.geometry.crop_roi"), node_id="crop")
        g.connect("load", "image", "crop", "image")
        wf = tmp_path / "crop.cvflow.json"
        save_workflow(g, wf)

        code = main(["run", str(wf), "--target", "crop", "--set", "crop.rect=1,2"])
        assert code == 2
        assert "x,y,w,h" in capsys.readouterr().err

    def test_bad_override_is_friendly(self, demo_workflow, capsys):
        code = main(["run", str(demo_workflow), "--set", "blur.banana=1"])
        assert code == 2
        assert "no param" in capsys.readouterr().err

    def test_no_sinks_dry_run_writes_nothing(self, demo_workflow):
        code = main(["run", str(demo_workflow), "--no-sinks",
                     "--target", "canny"])
        assert code == 0
        assert not (demo_workflow.parent / "out").exists()

    def test_target_prints_summary(self, demo_workflow, capsys):
        main(["run", str(demo_workflow), "--no-sinks", "--target", "canny"])
        out = capsys.readouterr().out
        assert "canny.edges: BINARY" in out

    def test_validate(self, demo_workflow, capsys):
        code = main(["validate", str(demo_workflow)])
        assert code == 0
        assert "5 node(s), 4 edge(s)" in capsys.readouterr().out

    def test_nodes_list(self, capsys):
        code = main(["nodes", "list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "cvflow.filters.gaussian_blur" in out

    def test_node_error_exits_nonzero(self, demo_workflow, capsys):
        # point the loader at a missing file
        code = main(["run", str(demo_workflow),
                     "--set", "load.path=nope.png"])
        assert code == 1
        assert "not found" in capsys.readouterr().err
