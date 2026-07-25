"""Performance gate (docs/01 N1, docs/08 Phase 0 exit criteria).

Asserts the product promise in CI: after a warm run, changing one parameter
re-executes only the affected suffix, and the warm param-to-result loop on a
1080p image stays inside budget. The budget is deliberately looser than the
interactive target (100 ms) to absorb CI machine variance without flaking.
"""

import time

import cv2
import numpy as np
import pytest

from cvflow.core.graph import Graph
from cvflow.engine import EngineSettings, ExecutionService, NodeStatus
from cvflow.plugins import builtin_registry

WARM_BUDGET_MS = 150.0


@pytest.fixture
def hd_pipeline(tmp_path):
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
    src = tmp_path / "hd.png"
    cv2.imwrite(str(src), frame)

    registry, _ = builtin_registry()
    g = Graph()
    g.add_node(registry.get("cvflow.io.load_image"), node_id="load",
               params={"path": str(src)})
    g.add_node(registry.get("cvflow.color.to_gray"), node_id="gray")
    g.add_node(registry.get("cvflow.filters.gaussian_blur"), node_id="blur")
    g.add_node(registry.get("cvflow.edges.canny"), node_id="canny")
    g.connect("load", "image", "gray", "image")
    g.connect("gray", "out", "blur", "image")
    g.connect("blur", "out", "canny", "image")
    return g


def test_warm_param_change_is_incremental_and_fast(hd_pipeline):
    svc = ExecutionService(hd_pipeline, EngineSettings(workers=0))
    svc.run(observed=["canny"])  # cold run fills the cache

    hd_pipeline.set_param("canny", "low", 80)
    t0 = time.perf_counter()
    report = svc.run(observed=["canny"])
    elapsed_ms = (time.perf_counter() - t0) * 1000

    for nid in ("load", "gray", "blur"):
        assert report.nodes[nid].status is NodeStatus.CACHED, report.to_text()
    assert report.nodes["canny"].status is NodeStatus.OK

    assert elapsed_ms < WARM_BUDGET_MS, (
        f"warm param change took {elapsed_ms:.1f} ms "
        f"(budget {WARM_BUDGET_MS} ms)\n{report.to_text()}")
