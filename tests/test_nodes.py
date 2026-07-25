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


class TestNewFilters:
    """median / box / bilateral / unsharp (session 4)."""

    def test_median_removes_salt_and_pepper(self, full_registry):
        spec = full_registry.get("cvflow.filters.median_blur")
        rng = np.random.default_rng(3)
        flat = np.full((64, 64), 128, np.uint8)
        noisy = flat.copy()
        ys, xs = rng.integers(0, 64, 60), rng.integers(0, 64, 60)
        noisy[ys, xs] = 255  # sparse impulses — median's home turf
        from cvflow.core.types.image import ImageBuffer

        out = run_node(spec.node_class,
                       inputs={"image": ImageBuffer(noisy, "GRAY")},
                       params={"kernel": 5})["out"]
        assert np.abs(out.data.astype(int) - 128).max() < \
            np.abs(noisy.astype(int) - 128).max()

    def test_median_keeps_a_mask_binary(self, full_registry):
        """A rank filter only emits values that were already present, so unlike
        the averaging filters it can honestly keep the BINARY label."""
        spec = full_registry.get("cvflow.filters.median_blur")
        out = run_node(spec.node_class,
                       inputs={"image": checker_image(64, cell=1, space="BINARY")},
                       params={"kernel": 3})["out"]
        assert out.space is ColorSpace.BINARY
        assert set(np.unique(out.data)) <= {0, 255}

    @pytest.mark.parametrize("type_id,params", [
        ("cvflow.filters.box_blur", {"kernel": 5}),
        ("cvflow.filters.gaussian_blur", {"kernel": 5}),
        ("cvflow.filters.bilateral", {"diameter": 9}),
        ("cvflow.filters.unsharp_mask", {"radius": 5, "amount": 1.0}),
    ])
    def test_blending_filters_downgrade_binary_to_gray(self, full_registry,
                                                       type_id, params):
        """These all blend neighbours, so the result is no longer {0,255}.
        Emitting GRAY is the honest option — silently keeping the BINARY label
        is the bug CODE_REVIEW §2.8 found in Resize."""
        spec = full_registry.get(type_id)
        out = run_node(spec.node_class,
                       inputs={"image": checker_image(64, cell=1, space="BINARY")},
                       params=params)["out"]
        assert out.space is ColorSpace.GRAY, f"{type_id} mislabelled its output"

    def test_box_blur_smooths(self, full_registry):
        spec = full_registry.get("cvflow.filters.box_blur")
        src = checker_image(64, space="GRAY")
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"kernel": 9})["out"]
        assert float(out.data.std()) < float(src.data.std())

    def test_bilateral_preserves_edges_better_than_box(self, full_registry):
        """The whole point of the node: at comparable smoothing strength it
        keeps more edge contrast than a plain mean."""
        src = shapes_image(128, space="BGR")
        bilateral = run_node(
            full_registry.get("cvflow.filters.bilateral").node_class,
            inputs={"image": src},
            params={"diameter": 9, "sigma_color": 50.0, "sigma_space": 50.0})["out"]
        box = run_node(full_registry.get("cvflow.filters.box_blur").node_class,
                       inputs={"image": src}, params={"kernel": 9})["out"]

        def edge_energy(buf):
            import cv2
            gray = cv2.cvtColor(buf.data, cv2.COLOR_BGR2GRAY)
            return float(np.abs(cv2.Laplacian(gray, cv2.CV_32F)).mean())

        assert edge_energy(bilateral) > edge_energy(box)

    def test_unsharp_amount_zero_is_a_noop(self, full_registry):
        spec = full_registry.get("cvflow.filters.unsharp_mask")
        src = shapes_image(64)
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"radius": 5, "amount": 0.0})["out"]
        assert np.array_equal(out.data, src.data)

    def test_unsharp_increases_local_contrast(self, full_registry):
        spec = full_registry.get("cvflow.filters.unsharp_mask")
        src = shapes_image(128)
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"radius": 5, "amount": 1.5})["out"]
        assert float(out.data.std()) > float(src.data.std())


class TestSobelAndLaplacian:
    def _gray(self, full_registry, size=128):
        return run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(size)})["out"]

    @pytest.mark.parametrize("type_id", ["cvflow.edges.sobel",
                                         "cvflow.edges.laplacian"])
    def test_normalized_output_is_8bit_gray(self, full_registry, type_id):
        spec = full_registry.get(type_id)
        out = run_node(spec.node_class,
                       inputs={"image": self._gray(full_registry)},
                       params={"normalize": True})["out"]
        assert out.space is ColorSpace.GRAY
        assert out.data.dtype == np.uint8
        assert out.data.max() > 0  # shapes produce gradients

    @pytest.mark.parametrize("type_id", ["cvflow.edges.sobel",
                                         "cvflow.edges.laplacian"])
    def test_raw_output_is_float_and_arbitrary_range(self, full_registry, type_id):
        """Unnormalized derivatives are signed and unbounded; labelling them
        ARBITRARY is what stops the viewer clipping negatives to black."""
        from cvflow.core.types.image import ValueRange

        spec = full_registry.get(type_id)
        out = run_node(spec.node_class,
                       inputs={"image": self._gray(full_registry)},
                       params={"normalize": False})["out"]
        assert out.data.dtype == np.float32
        assert out.range is ValueRange.ARBITRARY

    def test_sobel_x_and_y_differ_on_an_oriented_edge(self, full_registry):
        from cvflow.core.types.image import ImageBuffer

        # A purely vertical edge: gx responds, gy should not.
        arr = np.zeros((64, 64), np.uint8)
        arr[:, 32:] = 255
        src = ImageBuffer(arr, "GRAY")
        spec = full_registry.get("cvflow.edges.sobel")
        gx = run_node(spec.node_class, inputs={"image": src},
                      params={"direction": "x", "normalize": False})["out"]
        gy = run_node(spec.node_class, inputs={"image": src},
                      params={"direction": "y", "normalize": False})["out"]
        assert np.abs(gx.data).max() > 0
        assert np.abs(gy.data).max() == 0


class TestInRange:
    def _hsv_swatch(self):
        """Left half pure red, right half pure blue, in HSV."""
        import cv2
        from cvflow.core.types.image import ImageBuffer

        bgr = np.zeros((32, 64, 3), np.uint8)
        bgr[:, :32] = (0, 0, 255)    # red
        bgr[:, 32:] = (255, 0, 0)    # blue
        return ImageBuffer(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), "HSV")

    def test_selects_one_hue_band(self, full_registry):
        spec = full_registry.get("cvflow.color.in_range")
        out = run_node(spec.node_class, inputs={"image": self._hsv_swatch()},
                       params={"low1": 0, "high1": 10, "low2": 100, "high2": 255,
                               "low3": 100, "high3": 255})["mask"]
        assert out.space is ColorSpace.BINARY
        assert set(np.unique(out.data)) <= {0, 255}
        assert (out.data[:, :32] == 255).all()   # red half selected
        assert (out.data[:, 32:] == 0).all()     # blue half rejected

    def test_single_channel_uses_only_channel_one(self, full_registry):
        spec = full_registry.get("cvflow.color.in_range")
        src = checker_image(32, space="GRAY")  # values are 0 and 255
        mask = run_node(spec.node_class, inputs={"image": src},
                        params={"low1": 200, "high1": 255})["mask"]
        assert np.array_equal(mask.data == 255, src.data == 255)

    def test_inverted_band_is_a_config_error(self, full_registry):
        spec = full_registry.get("cvflow.color.in_range")
        issues = spec.node_class().validate(
            {"low1": 200, "high1": 10, "low2": 0, "high2": 255,
             "low3": 0, "high3": 255})
        assert issues and issues[0].level == "error"


class TestClahe:
    def test_boosts_local_contrast_on_gray(self, full_registry):
        from cvflow.core.types.image import ImageBuffer

        spec = full_registry.get("cvflow.color.clahe")
        # A low-contrast gradient: global range is small, so CLAHE has room.
        ramp = np.tile(np.linspace(100, 140, 64, dtype=np.uint8), (64, 1))
        out = run_node(spec.node_class, inputs={"image": ImageBuffer(ramp, "GRAY")},
                       params={"clip": 4.0, "tiles": 8})["out"]
        assert out.space is ColorSpace.GRAY
        assert float(out.data.std()) > float(ramp.std())

    def test_colour_path_keeps_bgr(self, full_registry):
        spec = full_registry.get("cvflow.color.clahe")
        out = run_node(spec.node_class, inputs={"image": shapes_image(64)},
                       params={"clip": 2.0, "tiles": 8})["out"]
        assert out.space is ColorSpace.BGR
        assert out.data.shape == (64, 64, 3)

    def test_rejects_a_space_it_cannot_equalize(self, full_registry):
        """HSV's channels can't take a per-channel curve without wrecking the
        colour, so refuse rather than silently mangle it."""
        import cv2
        from cvflow.core.types.image import ImageBuffer

        spec = full_registry.get("cvflow.color.clahe")
        hsv = ImageBuffer(cv2.cvtColor(shapes_image(64).data, cv2.COLOR_BGR2HSV),
                          "HSV")
        with pytest.raises(NodeExecutionError):
            run_node(spec.node_class, inputs={"image": hsv}, params={})


class TestRotateFlip:
    def test_rotation_transposes_dimensions(self, full_registry):
        spec = full_registry.get("cvflow.geometry.rotate_flip")
        src = shapes_image(128)
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"rotate": "90 cw", "flip": "none"})["out"]
        assert (out.width, out.height) == (src.height, src.width)

    def test_four_quarter_turns_return_the_original(self, full_registry):
        spec = full_registry.get("cvflow.geometry.rotate_flip")
        src = shapes_image(64)
        buf = src
        for _ in range(4):
            buf = run_node(spec.node_class, inputs={"image": buf},
                           params={"rotate": "90 cw", "flip": "none"})["out"]
        assert np.array_equal(buf.data, src.data)

    def test_double_flip_is_identity(self, full_registry):
        spec = full_registry.get("cvflow.geometry.rotate_flip")
        src = shapes_image(64)
        once = run_node(spec.node_class, inputs={"image": src},
                        params={"rotate": "none", "flip": "horizontal"})["out"]
        twice = run_node(spec.node_class, inputs={"image": once},
                         params={"rotate": "none", "flip": "horizontal"})["out"]
        assert not np.array_equal(once.data, src.data)
        assert np.array_equal(twice.data, src.data)

    def test_no_op_still_returns_a_valid_output(self, full_registry):
        """Both settings 'none' must not hand the frozen input array straight
        back out as a new output buffer."""
        spec = full_registry.get("cvflow.geometry.rotate_flip")
        src = checker_image(32, space="BINARY")
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"rotate": "none", "flip": "none"})["out"]
        assert np.array_equal(out.data, src.data)
        assert out.data is not src.data
        assert out.space is ColorSpace.BINARY  # rearrangement keeps the mask


class TestCropRoi:
    def test_crops_to_the_rect(self, full_registry):
        spec = full_registry.get("cvflow.geometry.crop_roi")
        out = run_node(spec.node_class, inputs={"image": shapes_image(128)},
                       params={"rect": (10, 20, 40, 30)})["out"]
        assert (out.width, out.height) == (40, 30)

    def test_zero_extent_means_to_the_edge(self, full_registry):
        """Keeps the default rect a pass-through instead of a node that
        silently emits nothing."""
        spec = full_registry.get("cvflow.geometry.crop_roi")
        src = shapes_image(64)
        out = run_node(spec.node_class, inputs={"image": src},
                       params={"rect": (0, 0, 0, 0)})["out"]
        assert (out.width, out.height) == (src.width, src.height)

    def test_oversized_rect_is_clipped_not_an_error(self, full_registry):
        """A fixed ROI must keep working when the input resolution changes."""
        spec = full_registry.get("cvflow.geometry.crop_roi")
        out = run_node(spec.node_class, inputs={"image": shapes_image(64)},
                       params={"rect": (32, 32, 500, 500)})["out"]
        assert (out.width, out.height) == (32, 32)

    def test_rect_entirely_outside_is_an_error(self, full_registry):
        spec = full_registry.get("cvflow.geometry.crop_roi")
        with pytest.raises(NodeExecutionError):
            run_node(spec.node_class, inputs={"image": shapes_image(64)},
                     params={"rect": (500, 500, 10, 10)})

    def test_output_is_frozen_even_when_sharing_memory(self, full_registry):
        """copy=False hands out a view of the input; it must still be frozen,
        or a downstream node could mutate its own upstream's cached buffer."""
        spec = full_registry.get("cvflow.geometry.crop_roi")
        out = run_node(spec.node_class, inputs={"image": shapes_image(64)},
                       params={"rect": (0, 0, 16, 16), "copy": False})["out"]
        assert not out.data.flags.writeable


class TestFilterContours:
    def _contours(self, full_registry, min_area=0.0):
        gray = run_node(full_registry.get("cvflow.color.to_gray").node_class,
                        inputs={"image": shapes_image(256)})["out"]
        binary = run_node(full_registry.get("cvflow.threshold.threshold").node_class,
                          inputs={"image": gray},
                          params={"method": "otsu"})["out"]
        return run_node(full_registry.get("cvflow.analysis.find_contours").node_class,
                        inputs={"image": binary},
                        params={"min_area": min_area})["contours"]

    def test_area_band_drops_out_of_range_contours(self, full_registry):
        spec = full_registry.get("cvflow.analysis.filter_contours")
        source = self._contours(full_registry)
        assert len(source) > 0
        areas = sorted(source.areas())
        cutoff = areas[-1]  # keep only the largest

        out = run_node(spec.node_class, inputs={"contours": source},
                       params={"area": (cutoff - 1.0, cutoff + 1.0)})["out"]
        assert 0 < len(out) < len(source) or len(source) == 1
        assert all(cutoff - 1.0 <= a <= cutoff + 1.0 for a in out.areas())

    def test_invert_returns_the_complement(self, full_registry):
        spec = full_registry.get("cvflow.analysis.filter_contours")
        source = self._contours(full_registry)
        band = {"area": (0.0, sorted(source.areas())[0] + 0.5)}
        kept = run_node(spec.node_class, inputs={"contours": source},
                        params=band)["out"]
        dropped = run_node(spec.node_class, inputs={"contours": source},
                           params={**band, "invert": True})["out"]
        assert len(kept) + len(dropped) == len(source)

    def test_ref_size_survives_filtering(self, full_registry):
        spec = full_registry.get("cvflow.analysis.filter_contours")
        source = self._contours(full_registry)
        out = run_node(spec.node_class, inputs={"contours": source},
                       params={})["out"]
        assert out.ref_size == source.ref_size


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

    def test_binary_stays_binary_whatever_the_interpolation(self, full_registry):
        """CODE_REVIEW §2.8 — linear/cubic/area blend neighbours, so a resized
        mask acquired in-between values while still labelled BINARY. Nothing
        downstream catches it: ImageBuffer validates dtype, not the {0,255}
        convention.

        ``cell=1`` matters. The default 8-px checker survives a 0.5 scale even
        with area interpolation, because every 2x2 source region falls inside
        one uniform block — so a coarser mask would let the bug through.
        """
        spec = full_registry.get("cvflow.geometry.resize")
        src = checker_image(64, cell=1, space="BINARY")
        for interp in ("linear", "cubic", "area", "nearest"):
            for scale in (0.5, 0.37):
                out = run_node(spec.node_class, inputs={"image": src},
                               params={"mode": "scale", "scale": scale,
                                       "interp": interp})["out"]
                assert out.space is ColorSpace.BINARY
                stray = set(np.unique(out.data)) - {0, 255}
                assert not stray, (
                    f"{interp} at scale {scale} produced {sorted(stray)[:5]}, "
                    f"outside {{0, 255}}")


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
