"""Workflow persistence: roundtrip fidelity, permissive-where-safe loading."""

import json

import pytest

from cvflow.core.errors import UnknownNodeTypeError, WorkflowFormatError
from cvflow.io.workflow_json import SCHEMA_VERSION, load_workflow, save_workflow


@pytest.fixture
def saved(chain_graph, registry, tmp_path):
    chain_graph.nodes["add1"].pos = (120.0, -40.5)
    chain_graph.nodes["add1"].label = "Brighten"
    chain_graph.set_param("add1", "amount", 25)
    path = tmp_path / "wf.cvflow.json"
    save_workflow(chain_graph, path, metadata={"title": "Test workflow"})
    return path


class TestRoundtrip:
    def test_topology_params_positions_survive(self, saved, registry):
        result = load_workflow(saved, registry)
        g = result.graph
        assert set(g.nodes) == {"src", "add1", "add2", "mean"}
        assert len(g.edges) == 3
        assert g.nodes["add1"].params["amount"] == 25
        assert g.nodes["add1"].pos == (120.0, -40.5)
        assert g.nodes["add1"].label == "Brighten"
        assert result.metadata["title"] == "Test workflow"
        assert not result.issues

    def test_file_is_versioned_readable_json(self, saved):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        assert doc["format"] == "cvflow-workflow"
        assert doc["schema_version"] == SCHEMA_VERSION
        assert "graph" in doc and "ui" in doc and "metadata" in doc

    def test_base_dir_is_workflow_parent(self, saved, registry):
        result = load_workflow(saved, registry)
        assert result.base_dir == str(saved.parent)


class TestRobustLoading:
    def test_unknown_node_type_raises_helpful_error(self, saved, registry):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        doc["graph"]["nodes"][0]["type"] = "missing.plugin.node"
        saved.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(UnknownNodeTypeError, match="plugin"):
            load_workflow(saved, registry)

    def test_unknown_param_dropped_with_issue(self, saved, registry):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        next(n for n in doc["graph"]["nodes"]
             if n["id"] == "add1")["params"]["ghost"] = 1
        saved.write_text(json.dumps(doc), encoding="utf-8")
        result = load_workflow(saved, registry)
        assert any("ghost" in issue for issue in result.issues)
        assert "ghost" not in result.graph.nodes["add1"].params

    def test_invalid_param_value_falls_back_to_default(self, saved, registry):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        next(n for n in doc["graph"]["nodes"]
             if n["id"] == "add1")["params"]["amount"] = "banana"
        saved.write_text(json.dumps(doc), encoding="utf-8")
        result = load_workflow(saved, registry)
        assert result.graph.nodes["add1"].params["amount"] == 10  # spec default
        assert any("amount" in issue for issue in result.issues)

    def test_bad_edge_skipped_with_issue(self, saved, registry):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        doc["graph"]["edges"].append({"from": ["mean", "value"],
                                      "to": ["add2", "image"]})  # Number->Image
        saved.write_text(json.dumps(doc), encoding="utf-8")
        result = load_workflow(saved, registry)
        assert len(result.graph.edges) == 3
        assert any("skipped edge" in issue for issue in result.issues)

    def test_newer_schema_refused_clearly(self, saved, registry):
        doc = json.loads(saved.read_text(encoding="utf-8"))
        doc["schema_version"] = 99
        saved.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(WorkflowFormatError, match="newer"):
            load_workflow(saved, registry)

    def test_not_json_refused_clearly(self, tmp_path, registry):
        path = tmp_path / "broken.cvflow.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(WorkflowFormatError, match="JSON"):
            load_workflow(path, registry)
