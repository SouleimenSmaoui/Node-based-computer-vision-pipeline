"""Built-in node behavior + registry conformance sweep (docs/04 §8)."""

import numpy as np
import pytest

from cvflow.core.errors import NodeExecutionError
from cvflow.core.types.image import ColorSpace
from cvflow.plugins import builtin_registry
from cvflow.sdk.testing import checker_image, run_node, shapes_image


@pytest.fixture(scope="module")
def full_registry():
    registry, failures = builtin_registry()
    assert not failures, [f.error for f in failures]
    return registry


class TestConformanceSweep:
    """Every registered node must have a sane, complete spec."""

    def test_specs_are_complete(self, full_registry):
        specs = full_registry.all_specs()
        assert len(specs) >= 5
        for spec in specs:
            assert spec.label and spec.category and spec.doc, spec.type_id
            assert spec.type_id.count(".") >= 1, spec.type_id
            for port in (*spec.inputs, *spec.outputs):
                assert port.name and port.label, (spec.type_id, port)
            for param in spec.params:
                assert param.name and param.label, (spec.type_id, param.name)
                # defaults must round-trip the param's own validation
                if param.default is not None:
                    param.validate(param.default)

    def test_search_finds_gaussian(self, full_registry):
        hits = full_registry.search("smooth")
        assert any(s.type_id == "cvflow.filters.gaussian_blur" for s in hits)


class TestGaussianBlur:
    def test_smooths_and_preserves_space(self, full_registry):
        spec = full_registry.get("cvflow.filters.gaussian_blur")
        src = checker_image(64, space="GRAY")
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"kernel": 9, "sigma": 2.0})
        assert out["out"].space is ColorSpace.GRAY
        assert float(out["out"].data.std()) < float(src.data.std())

    def test_does_not_mutate_input(self, full_registry):
        spec = full_registry.get("cvflow.filters.gaussian_blur")
        src = checker_image(32)
        before = src.data.copy()
        run_node(spec.node_class, inputs={"image": src}, params={"kernel": 5})
        assert (src.data == before).all()


class TestToGray:
    def test_bgr_to_gray(self, full_registry):
        spec = full_registry.get("cvflow.color.to_gray")
        out = run_node(spec.node_class, inputs={"image": shapes_image(64)})
        assert out["out"].space is ColorSpace.GRAY
        assert out["out"].data.ndim == 2

    def test_gray_passthrough(self, full_registry):
        spec = full_registry.get("cvflow.color.to_gray")
        out = run_node(spec.node_class, inputs={"image": checker_image(32)})
        assert out["out"].space is ColorSpace.GRAY


class TestCanny:
    def test_outputs_binary_edge_map(self, full_registry):
        spec = full_registry.get("cvflow.edges.canny")
        gray = run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(128)})["out"]
        out = run_node(spec.node_class, inputs={"image": gray},
                       params={"low": 60, "high": 160})
        edges = out["edges"]
        assert edges.space is ColorSpace.BINARY
        assert set(np.unique(edges.data)) <= {0, 255}
        assert (edges.data == 255).sum() > 0  # shapes produce edges

    def test_threshold_order_validates(self, full_registry):
        spec = full_registry.get("cvflow.edges.canny")
        issues = spec.node_class().validate(
            {"low": 200, "high": 100, "aperture": "3", "l2": False})
        assert issues and issues[0].level == "error"


class TestThreshold:
    def _gray(self, full_registry, size=128):
        return run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(size)})["out"]

    def test_global_produces_binary(self, full_registry):
        spec = full_registry.get("cvflow.threshold.threshold")
        out = run_node(spec.node_class, inputs={"image": self._gray(full_registry)},
                       params={"method": "global", "thresh": 100})["out"]
        assert out.space is ColorSpace.BINARY
        assert set(np.unique(out.data)) <= {0, 255}

    def test_invert_flips_foreground(self, full_registry):
        spec = full_registry.get("cvflow.threshold.threshold")
        gray = self._gray(full_registry)
        normal = run_node(spec.node_class, inputs={"image": gray},
                          params={"method": "global", "thresh": 100})["out"]
        inv = run_node(spec.node_class, inputs={"image": gray},
                       params={"method": "global", "thresh": 100, "invert": True})["out"]
        assert (normal.data == (255 - inv.data)).all()

    def test_adaptive_runs(self, full_registry):
        spec = full_registry.get("cvflow.threshold.threshold")
        out = run_node(spec.node_class, inputs={"image": self._gray(full_registry)},
                       params={"method": "adaptive gaussian", "block_size": 9})["out"]
        assert out.space is ColorSpace.BINARY


class TestMorphology:
    def test_dilate_grows_foreground(self, full_registry):
        spec = full_registry.get("cvflow.morphology.morphology")
        src = checker_image(64, space="BINARY")
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"op": "dilate", "ksize": 3})["out"]
        assert out.space is ColorSpace.BINARY
        assert (out.data == 255).sum() >= (src.data == 255).sum()

    def test_erode_shrinks_foreground(self, full_registry):
        spec = full_registry.get("cvflow.morphology.morphology")
        src = checker_image(64, space="BINARY")
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"op": "erode", "ksize": 3})["out"]
        assert (out.data == 255).sum() <= (src.data == 255).sum()


class TestResize:
    def test_scale_halves_dimensions(self, full_registry):
        spec = full_registry.get("cvflow.geometry.resize")
        out = run_node(spec.node_class, inputs={"image": shapes_image(128)},
                       params={"mode": "scale", "scale": 0.5})["out"]
        assert (out.width, out.height) == (64, 64)
        assert out.space is ColorSpace.BGR

    def test_absolute_dimensions(self, full_registry):
        spec = full_registry.get("cvflow.geometry.resize")
        out = run_node(spec.node_class, inputs={"image": shapes_image(128)},
                       params={"mode": "absolute", "width": 200, "height": 100})["out"]
        assert (out.width, out.height) == (200, 100)


class TestInvert:
    def test_negative(self, full_registry):
        spec = full_registry.get("cvflow.filters.invert")
        src = checker_image(32)
        out = run_node(spec.node_class, inputs={"image": src})["out"]
        assert (out.data == 255 - src.data).all()
        assert out.space is src.space


class TestContours:
    def _mask(self, full_registry):
        gray = run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(128)})["out"]
        return run_node(full_registry.get("cvflow.threshold.threshold").node_class,
                        inputs={"image": gray}, params={"method": "otsu"})["out"]

    def test_find_contours_on_shapes(self, full_registry):
        from cvflow.core.types.geometry import ContourSet

        spec = full_registry.get("cvflow.analysis.find_contours")
        out = run_node(spec.node_class, inputs={"image": self._mask(full_registry)},
                       params={"mode": "external"})["contours"]
        assert isinstance(out, ContourSet)
        assert len(out) >= 2  # rectangle + circle
        assert out.ref_size == (128, 128)

    def test_min_area_filters(self, full_registry):
        spec = full_registry.get("cvflow.analysis.find_contours")
        mask = self._mask(full_registry)
        many = run_node(spec.node_class, inputs={"image": mask},
                        params={"min_area": 0.0})["contours"]
        few = run_node(spec.node_class, inputs={"image": mask},
                       params={"min_area": 1e6})["contours"]
        assert len(few) <= len(many)

    def test_draw_contours_outputs_bgr(self, full_registry):
        find = full_registry.get("cvflow.analysis.find_contours")
        draw = full_registry.get("cvflow.draw.draw_contours")
        mask = self._mask(full_registry)
        contours = run_node(find.node_class, inputs={"image": mask})["contours"]
        gray = run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(128)})["out"]
        out = run_node(draw.node_class,
                       inputs={"image": gray, "contours": contours},
                       params={"color": "red", "thickness": 2})["out"]
        assert out.space is ColorSpace.BGR
        assert out.channels == 3
        assert (out.data[:, :, 2] == 255).any()  # some red drawn


class TestLoadSaveImage:
    def test_roundtrip_via_disk(self, full_registry, tmp_path):
        save_spec = full_registry.get("cvflow.io.save_image")
        load_spec = full_registry.get("cvflow.io.load_image")
        src = shapes_image(64)
        target = tmp_path / "img.png"

        run_node(save_spec.node_class, inputs={"image": src},
                 params={"path": str(target)})
        assert target.exists()

        out = run_node(load_spec.node_class, params={"path": str(target)})
        assert out["image"].space is ColorSpace.BGR
        assert (out["image"].data == src.data).all()  # png is lossless

    def test_missing_file_is_clear_error(self, full_registry):
        spec = full_registry.get("cvflow.io.load_image")
        with pytest.raises(NodeExecutionError, match="not found"):
            run_node(spec.node_class, params={"path": "definitely_missing.png"})

    def test_external_state_tracks_file_changes(self, full_registry, tmp_path):
        import os

        spec = full_registry.get("cvflow.io.load_image")
        target = tmp_path / "img.png"
        run_node(full_registry.get("cvflow.io.save_image").node_class,
                 inputs={"image": shapes_image(32)}, params={"path": str(target)})

        params = {"path": str(target)}
        state1 = spec.node_class.external_state(params, None)
        os.utime(target, (1_000_000, 1_000_000))  # simulate file replaced
        state2 = spec.node_class.external_state(params, None)
        assert state1 != state2

    def test_relative_path_resolves_against_base_dir(self, full_registry, tmp_path):
        from cvflow.engine.context import Resources

        run_node(full_registry.get("cvflow.io.save_image").node_class,
                 inputs={"image": shapes_image(32)},
                 params={"path": str(tmp_path / "rel.png")})
        out = run_node(full_registry.get("cvflow.io.load_image").node_class,
                       params={"path": "rel.png"},
                       resources=Resources(base_dir=str(tmp_path)))
        assert out["image"].width == 32
