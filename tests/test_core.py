"""Core model invariants: params, types, graph structure."""

import numpy as np
import pytest

from cvflow.core.errors import ConnectionTypeError, CycleError, ParamError
from cvflow.core.params import FloatParam, IntParam, validate_params
from cvflow.core.types.base import Coerce, Ok, PortType, Reject, check_connection
from cvflow.core.types.image import ColorSpace, ImageBuffer


class TestParams:
    def test_int_clamps_to_range(self):
        spec = IntParam("K", default=5, min=1, max=9)
        spec.__set_name__(object, "k")
        assert spec.validate(50) == 9
        assert spec.validate(-3) == 1

    def test_int_snaps_to_odd(self):
        spec = IntParam("K", default=5, min=1, max=99, odd_only=True)
        spec.__set_name__(object, "k")
        assert spec.validate(4) == 5
        assert spec.validate(7) == 7

    def test_type_mismatch_raises(self):
        spec = FloatParam("S", default=0.0)
        spec.__set_name__(object, "s")
        with pytest.raises(ParamError):
            spec.validate("not a number")

    def test_unknown_param_rejected(self):
        spec = IntParam("K", default=5)
        spec.__set_name__(object, "k")
        with pytest.raises(ParamError, match="unknown parameter"):
            validate_params([spec], {"nope": 1})


class TestImageBuffer:
    def test_output_arrays_are_frozen(self):
        buf = ImageBuffer(np.zeros((4, 4), np.uint8), ColorSpace.GRAY)
        with pytest.raises(ValueError):
            buf.data[0, 0] = 1

    def test_writable_copy_is_independent(self):
        buf = ImageBuffer(np.zeros((4, 4), np.uint8), ColorSpace.GRAY)
        copy = buf.writable_copy()
        copy[0, 0] = 7
        assert buf.data[0, 0] == 0

    def test_channel_count_must_match_space(self):
        with pytest.raises(ValueError, match="3 channel"):
            ImageBuffer(np.zeros((4, 4), np.uint8), ColorSpace.BGR)

    def test_derive_inherits_and_freezes(self):
        buf = ImageBuffer(np.zeros((4, 4), np.uint8), ColorSpace.GRAY,
                          meta={"path": "x.png"})
        out = buf.derive(np.ones((4, 4, 3), np.uint8), space="BGR")
        assert out.space is ColorSpace.BGR
        assert out.meta["path"] == "x.png"
        assert not out.data.flags.writeable


class TestConnectionRules:
    def test_same_space_ok(self):
        r = check_connection(PortType("image", ColorSpace.GRAY),
                             PortType("image", ColorSpace.GRAY))
        assert isinstance(r, Ok)

    def test_binary_satisfies_gray(self):
        r = check_connection(PortType("image", ColorSpace.BINARY),
                             PortType("image", ColorSpace.GRAY))
        assert isinstance(r, Coerce)

    def test_gray_to_bgr_coerces_with_replication(self):
        r = check_connection(PortType("image", ColorSpace.GRAY),
                             PortType("image", ColorSpace.BGR))
        assert isinstance(r, Coerce)
        out = r.fn(ImageBuffer(np.full((2, 2), 9, np.uint8), ColorSpace.GRAY))
        assert out.space is ColorSpace.BGR
        assert out.data.shape == (2, 2, 3)
        assert (out.data == 9).all()

    def test_bgr_to_gray_rejected_with_hint(self):
        r = check_connection(PortType("image", ColorSpace.BGR),
                             PortType("image", ColorSpace.GRAY))
        assert isinstance(r, Reject)
        assert "To Gray" in (r.hint or "")

    def test_cross_kind_rejected(self):
        r = check_connection(PortType("image"), PortType("number"))
        assert isinstance(r, Reject)


class TestGraph:
    def test_cycle_rejected(self, registry, chain_graph):
        with pytest.raises(CycleError):
            chain_graph.connect("add2", "out", "add1", "image")

    def test_self_loop_rejected(self, chain_graph):
        with pytest.raises(CycleError):
            chain_graph.connect("add1", "out", "add1", "image")

    def test_incompatible_connection_raises(self, registry):
        from cvflow.core.graph import Graph

        g = Graph()
        g.add_node(registry.get("test.mean"), node_id="m")
        g.add_node(registry.get("test.add"), node_id="a")
        with pytest.raises(ConnectionTypeError):
            g.connect("m", "value", "a", "image")  # Number -> Image

    def test_reconnect_replaces_input_edge(self, registry, chain_graph):
        # add2.image currently fed by add1; rewire to src
        chain_graph.connect("src", "out", "add2", "image")
        feeding = [e for e in chain_graph.edges if e.dst == ("add2", "image")]
        assert len(feeding) == 1
        assert feeding[0].src == ("src", "out")

    def test_topo_order_respects_dependencies(self, chain_graph):
        order = chain_graph.topo_order()
        assert order.index("src") < order.index("add1") < order.index("add2")
        assert order.index("add1") < order.index("mean")

    def test_ancestors_descendants(self, chain_graph):
        assert chain_graph.ancestors({"add2"}) == {"src", "add1"}
        assert chain_graph.descendants({"src"}) == {"add1", "add2", "mean"}

    def test_set_param_validates(self, chain_graph):
        assert chain_graph.set_param("add1", "amount", 999) == 255  # clamped
        with pytest.raises(Exception):
            chain_graph.set_param("add1", "no_such_param", 1)
