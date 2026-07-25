"""Core model invariants: params, types, graph structure."""

import numpy as np
import pytest

from cvflow.core.errors import ConnectionTypeError, CycleError, ParamError
from cvflow.core.params import (
    CodeParam,
    ColorParam,
    FloatParam,
    IntParam,
    PointParam,
    RangeParam,
    RectParam,
    validate_params,
)
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


class TestTupleParams:
    """RangeParam / PointParam / RectParam / ColorParam / CodeParam."""

    @staticmethod
    def _named(spec, name="p"):
        spec.__set_name__(object, name)
        return spec

    def test_range_swaps_a_crossed_band(self):
        """Snap-to-valid, like IntParam clamping: a slider dragged past its
        partner keeps both values rather than raising."""
        spec = self._named(RangeParam("Area", default=(0.0, 10.0)))
        assert spec.validate((8.0, 2.0)) == (2.0, 8.0)

    def test_range_clamps_both_ends(self):
        spec = self._named(RangeParam("Area", default=(0.0, 1.0), min=0.0, max=100.0))
        assert spec.validate((-5.0, 500.0)) == (0.0, 100.0)

    def test_range_integer_mode_rounds(self):
        spec = self._named(RangeParam("N", default=(0, 10), integer=True))
        assert spec.validate((1.6, 8.2)) == (2, 8)

    def test_rect_normalizes_a_backwards_drag(self):
        """Dragging up-and-left gives negative extents; normalize rather than
        reject, so the obvious gesture just works."""
        spec = self._named(RectParam("ROI"))
        assert spec.validate((100, 100, -40, -30)) == (60, 70, 40, 30)

    def test_rect_clip_to_image(self):
        assert RectParam.clip_to((-10, -10, 50, 50), 100, 100) == (0, 0, 40, 40)
        assert RectParam.clip_to((80, 80, 50, 50), 100, 100) == (80, 80, 20, 20)
        assert RectParam.clip_to((200, 200, 10, 10), 100, 100) == (100, 100, 0, 0)

    def test_color_is_bgr_and_clamped(self):
        spec = self._named(ColorParam("Colour", default=(0, 255, 0)))
        assert spec.validate((300, -20, 7)) == (255, 0, 7)
        assert len(spec.validate((1, 2, 3))) == 3

    def test_color_with_alpha_needs_four(self):
        spec = self._named(ColorParam("Colour", default=(0, 0, 0, 255),
                                      with_alpha=True))
        assert spec.validate((1, 2, 3, 4)) == (1, 2, 3, 4)
        with pytest.raises(ParamError):
            spec.validate((1, 2, 3))

    @pytest.mark.parametrize("spec_factory,text,expected", [
        (lambda: RangeParam("R", default=(0.0, 1.0)), "2,8", (2.0, 8.0)),
        (lambda: RangeParam("R", default=(0.0, 1.0)), "2:8", (2.0, 8.0)),
        (lambda: PointParam("P"), "10,20", (10, 20)),
        (lambda: RectParam("R"), "1,2,3,4", (1, 2, 3, 4)),
        (lambda: ColorParam("C"), "10,20,30", (10, 20, 30)),
    ])
    def test_cli_parse(self, spec_factory, text, expected):
        """`cvflow run --set node.roi=1,2,3,4` has to work for these too."""
        assert self._named(spec_factory()).parse(text) == expected

    def test_parse_rejects_wrong_arity(self):
        spec = self._named(RectParam("R"))
        with pytest.raises(ParamError):
            spec.parse("1,2,3")

    @pytest.mark.parametrize("spec_factory,value", [
        (lambda: RangeParam("R", default=(0.0, 1.0)), (2.0, 8.0)),
        (lambda: PointParam("P"), (10, 20)),
        (lambda: RectParam("R"), (1, 2, 3, 4)),
        (lambda: ColorParam("C"), (10, 20, 30)),
    ])
    def test_json_round_trip_preserves_the_value(self, spec_factory, value):
        """JSON turns tuples into lists. If from_json didn't restore the tuple,
        every reload would re-fingerprint and re-execute the whole graph."""
        import json

        spec = self._named(spec_factory())
        raw = json.loads(json.dumps(spec.to_json(value)))
        assert spec.from_json(raw) == value

    def test_tuple_specs_reject_scalars_and_bad_arity(self):
        spec = self._named(PointParam("P"))
        with pytest.raises(ParamError):
            spec.validate(5)
        with pytest.raises(ParamError):
            spec.validate((1, 2, 3))
        with pytest.raises(ParamError):
            spec.validate(("a", "b"))

    def test_code_param_is_a_string_param(self):
        spec = self._named(CodeParam("Script", default="x = 1"))
        assert spec.validate("y = 2") == "y = 2"
        assert spec.language == "python"
        with pytest.raises(ParamError):
            spec.validate(42)


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
