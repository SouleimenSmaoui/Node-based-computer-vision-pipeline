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


class TestParamSnapshotCoherence:
    """CODE_REVIEW §1.1 — one coherent params read per node per run.

    The GUI edits params without taking the run-lock. When the engine read
    ``inst.params`` once for the fingerprint and again at execution, an edit
    landing between the two made the node execute with the *new* value while
    caching the result under the *old* value's key. Nothing looks wrong until
    the user returns to the old value (slider back, or undo) — then the poisoned
    entry hits and a wrong image is displayed persistently.
    """

    def test_fingerprint_uses_the_snapshot_not_live_params(self, chain_graph):
        from cvflow.engine.cache import node_fingerprint

        inst = chain_graph.nodes["add2"]
        snap = dict(inst.params)
        fp = node_fingerprint(inst, [], None, params=snap)

        inst.params["amount"] = 99  # an edit lands after the snapshot was taken
        assert node_fingerprint(inst, [], None, params=snap) == fp
        assert node_fingerprint(inst, [], None) != fp  # a live read does see it

    def test_execute_node_ignores_edits_after_the_snapshot(self, chain_graph):
        """``_execute_node`` must use the snapshot it is handed — re-reading
        ``inst.params`` is the second read that made the race possible."""
        import cv2

        svc = make_service(chain_graph)
        svc.run(observed=["src"])
        source = svc.get_output("src", "out")

        inst = chain_graph.nodes["add1"]
        snap = dict(inst.params)
        inst.params["amount"] = 200  # live edit, after the snapshot

        outputs, _ = svc._execute_node("add1", inst, {"image": source}, None, snap)
        assert np.array_equal(outputs["out"].data,
                              cv2.add(source.data, snap["amount"]))

    def test_mid_dispatch_edit_cannot_poison_the_cache(self, chain_graph):
        """End-to-end: drop an edit into the exact window the race needs —
        between fingerprinting and execution, where ``_assemble_inputs`` runs.

        Patching that call is just a deterministic stand-in for the GUI thread
        winning the race; the assertion is on real cached output.
        """
        svc = make_service(chain_graph)

        # Ground truth for amount=42, computed with nothing interfering.
        chain_graph.set_param("add2", "amount", 42)
        svc.run(observed=["add2"])
        truth = svc.get_output("add2", "out").data.copy()
        svc.cache.clear()

        real_assemble = svc._assemble_inputs

        def racing_assemble(inst, values):
            if inst.id == "add2":  # the GUI edits mid-dispatch
                chain_graph.set_param("add2", "amount", 99)
            return real_assemble(inst, values)

        chain_graph.set_param("add2", "amount", 42)
        svc._assemble_inputs = racing_assemble
        try:
            svc.run(observed=["add2"])
        finally:
            svc._assemble_inputs = real_assemble

        # The user slides back to 42. Serving a cached +99 image here is the bug.
        chain_graph.set_param("add2", "amount", 42)
        report = svc.run(observed=["add2"])
        assert report.nodes["add2"].status is NodeStatus.CACHED
        assert np.array_equal(svc.get_output("add2", "out").data, truth)


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
