"""Engine invariants: incremental execution, caching, error isolation.

These are the Phase 0 exit criteria from docs/08 — asserted, not hoped.
"""

import numpy as np
import pytest

from cvflow.engine import EngineSettings, ExecutionService, NodeStatus
from cvflow.engine.cache import OutputCache

from conftest import AddNode, SourceNode


def make_service(graph, **kw) -> ExecutionService:
    kw.setdefault("workers", 0)  # inline = deterministic
    return ExecutionService(graph, EngineSettings(**kw))


class TestIncrementalExecution:
    def test_first_run_executes_demand_closure_only(self, chain_graph):
        svc = make_service(chain_graph)
        report = svc.run(observed=["add1"])
        # add2 and mean are not demanded by add1
        assert set(report.nodes) == {"src", "add1"}
        assert report.nodes["src"].status is NodeStatus.OK
        assert report.nodes["add1"].status is NodeStatus.OK

    def test_second_run_is_all_cache_hits(self, chain_graph):
        svc = make_service(chain_graph)
        svc.run(observed=["add2"])
        assert SourceNode.calls == 1 and AddNode.calls == 2
        report = svc.run(observed=["add2"])
        assert SourceNode.calls == 1 and AddNode.calls == 2  # nothing re-ran
        assert all(m.status is NodeStatus.CACHED for m in report.nodes.values())

    def test_param_change_reruns_only_downstream(self, chain_graph):
        """The core promise: tune add2, and src/add1 must come from cache."""
        svc = make_service(chain_graph)
        svc.run(observed=["add2"])
        chain_graph.set_param("add2", "amount", 42)
        report = svc.run(observed=["add2"])
        assert report.nodes["src"].status is NodeStatus.CACHED
        assert report.nodes["add1"].status is NodeStatus.CACHED
        assert report.nodes["add2"].status is NodeStatus.OK
        assert SourceNode.calls == 1
        assert AddNode.calls == 3  # add1 once, add2 twice

    def test_upstream_change_invalidates_downstream(self, chain_graph):
        svc = make_service(chain_graph)
        svc.run(observed=["add2"])
        chain_graph.set_param("src", "seed", 2)
        report = svc.run(observed=["add2"])
        assert all(m.status is NodeStatus.OK for m in report.nodes.values())

    def test_results_are_correct_after_cache_replay(self, chain_graph):
        svc = make_service(chain_graph)
        svc.run(observed=["mean"])
        first = svc.get_output("mean", "value")
        report = svc.run(observed=["mean"])
        assert report.nodes["mean"].status is NodeStatus.CACHED
        assert svc.get_output("mean", "value") == first

    def test_reverting_param_hits_old_cache_entry(self, chain_graph):
        svc = make_service(chain_graph)
        svc.run(observed=["add2"])
        chain_graph.set_param("add2", "amount", 42)
        svc.run(observed=["add2"])
        chain_graph.set_param("add2", "amount", 10)  # back to original
        report = svc.run(observed=["add2"])
        assert report.nodes["add2"].status is NodeStatus.CACHED


class TestErrorIsolation:
    def test_failure_blocks_descendants_not_siblings(self, registry):
        from cvflow.core.graph import Graph

        g = Graph()
        g.add_node(registry.get("test.source"), node_id="src")
        g.add_node(registry.get("test.fail"), node_id="bad")
        g.add_node(registry.get("test.add"), node_id="after_bad")
        g.add_node(registry.get("test.mean"), node_id="sibling")
        g.connect("src", "out", "bad", "image")
        g.connect("bad", "out", "after_bad", "image")
        g.connect("src", "out", "sibling", "image")

        svc = make_service(g)
        report = svc.run(observed=["after_bad", "sibling"])
        assert report.nodes["bad"].status is NodeStatus.ERROR
        assert report.nodes["after_bad"].status is NodeStatus.BLOCKED
        assert report.nodes["sibling"].status is NodeStatus.OK
        assert len(report.errors) == 1
        assert report.errors[0].node_id == "bad"
        assert "intentional test failure" in report.errors[0].message

    def test_missing_required_input_is_config_error(self, registry):
        from cvflow.core.graph import Graph

        g = Graph()
        g.add_node(registry.get("test.add"), node_id="orphan")
        svc = make_service(g)
        report = svc.run(observed=["orphan"])
        assert report.nodes["orphan"].status is NodeStatus.CONFIG_ERROR
        assert "not connected" in report.nodes["orphan"].error

    def test_run_with_no_targets_is_empty_noop(self, chain_graph):
        svc = make_service(chain_graph)
        report = svc.run(observed=[])
        assert report.nodes == {} and report.ok


class TestSideEffectPolicy:
    def test_unarmed_sink_is_skipped(self, registry, tmp_path):
        from cvflow.core.graph import Graph
        from cvflow.plugins import builtin_registry

        full, _ = builtin_registry()
        g = Graph()
        g.add_node(registry.get("test.source"), node_id="src")
        g.add_node(full.get("cvflow.io.save_image"), node_id="save",
                   params={"path": str(tmp_path / "x.png")})
        g.connect("src", "out", "save", "image")

        svc = make_service(g)
        report = svc.run(observed=["save"])  # observed but NOT armed
        assert report.nodes["save"].status is NodeStatus.SKIPPED
        assert not (tmp_path / "x.png").exists()

        report = svc.run(observed=["save"], armed=["save"])
        assert report.nodes["save"].status is NodeStatus.OK
        assert (tmp_path / "x.png").exists()


class TestCache:
    def test_budget_evicts_lru_first(self):
        cache = OutputCache(budget_bytes=3000)
        big = {"x": np.zeros(1000, np.uint8)}  # ~1000 bytes each
        for i in range(5):
            cache.put(f"fp{i}", dict(big))
        stats = cache.stats()
        assert stats.bytes_used <= 3000
        assert cache.get("fp0") is None       # oldest evicted
        assert cache.get("fp4") is not None   # newest kept

    def test_pinned_entries_survive_eviction(self):
        cache = OutputCache(budget_bytes=2500)
        cache.put("keep", {"x": np.zeros(1000, np.uint8)})
        cache.set_pinned({"keep"})
        for i in range(5):
            cache.put(f"fp{i}", {"x": np.zeros(1000, np.uint8)})
        assert cache.get("keep") is not None

    def test_parallel_run_matches_inline(self, chain_graph):
        inline = make_service(chain_graph, workers=0)
        inline.run(observed=["add2", "mean"])
        expected = inline.get_output("mean", "value")

        parallel = make_service(chain_graph, workers=4)
        parallel.cache.clear()
        parallel.run(observed=["add2", "mean"])
        assert parallel.get_output("mean", "value") == expected
