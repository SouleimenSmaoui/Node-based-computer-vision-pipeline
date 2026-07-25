"""Declarative parameter descriptors (docs/04 §1.1).

A node declares parameters as class attributes; the framework derives UI,
validation, serialization, and fingerprinting from these specs. Validation
policy: *snap to valid* (clamp range, snap step/odd) rather than raise — the
friendlier behavior for sliders and programmatic sweeps. Type mismatches and
unknown enum values still raise ``ParamError``.
"""

from __future__ import annotations

import enum
import math
from typing import Any, Callable, Sequence

from cvflow.core.errors import ParamError


class ParamSpec:
    """Base descriptor. Subclasses implement ``validate`` and ``parse``."""

    widget_hint = "input"

    def __init__(
        self,
        label: str,
        *,
        default: Any = None,
        tooltip: str = "",
        promotable: bool = False,
        live: bool = True,
    ):
        self.label = label
        self.default = default
        self.tooltip = tooltip
        self.promotable = promotable
        self.live = live
        self.name: str = ""  # filled by __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    # Values live in NodeInstance.params, not on Node classes; reading the
    # class attribute returns the spec itself (used by spec collection).
    def __get__(self, obj: Any, objtype: type | None = None) -> "ParamSpec":
        return self

    def validate(self, value: Any) -> Any:
        return value

    def parse(self, text: str) -> Any:
        """Parse a CLI string (``--set node.param=value``) into a value."""
        return self.validate(text)

    def to_json(self, value: Any) -> Any:
        return value

    def from_json(self, raw: Any) -> Any:
        return self.validate(raw)


class IntParam(ParamSpec):
    widget_hint = "slider"

    def __init__(
        self,
        label: str,
        *,
        default: int = 0,
        min: int | None = None,
        max: int | None = None,
        step: int = 1,
        odd_only: bool = False,
        **kw: Any,
    ):
        super().__init__(label, default=default, **kw)
        self.min, self.max, self.step, self.odd_only = min, max, step, odd_only

    def validate(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParamError(f"{self.name}: expected int, got {type(value).__name__}")
        v = int(round(value))
        if self.min is not None:
            v = max(v, self.min)
        if self.max is not None:
            v = min(v, self.max)
        if self.odd_only and v % 2 == 0:
            v += 1 if (self.max is None or v + 1 <= self.max) else -1
        return v

    def parse(self, text: str) -> int:
        try:
            return self.validate(int(text))
        except ValueError as e:
            raise ParamError(f"{self.name}: not an integer: {text!r}") from e


class FloatParam(ParamSpec):
    widget_hint = "slider"

    def __init__(
        self,
        label: str,
        *,
        default: float = 0.0,
        min: float | None = None,
        max: float | None = None,
        decimals: int = 3,
        **kw: Any,
    ):
        super().__init__(label, default=default, **kw)
        self.min, self.max, self.decimals = min, max, decimals

    def validate(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParamError(f"{self.name}: expected float, got {type(value).__name__}")
        v = float(value)
        if not math.isfinite(v):
            raise ParamError(f"{self.name}: must be finite, got {v}")
        if self.min is not None:
            v = max(v, self.min)
        if self.max is not None:
            v = min(v, self.max)
        return v

    def parse(self, text: str) -> float:
        try:
            return self.validate(float(text))
        except ValueError as e:
            raise ParamError(f"{self.name}: not a number: {text!r}") from e


class BoolParam(ParamSpec):
    widget_hint = "checkbox"

    def __init__(self, label: str, *, default: bool = False, **kw: Any):
        super().__init__(label, default=default, **kw)

    def validate(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ParamError(f"{self.name}: expected bool, got {type(value).__name__}")
        return value

    def parse(self, text: str) -> bool:
        lowered = text.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ParamError(f"{self.name}: not a boolean: {text!r}")


class EnumParam(ParamSpec):
    """Dropdown. ``choices`` is a sequence of string values (or an Enum class)."""

    widget_hint = "dropdown"

    def __init__(self, label: str, *, choices: Sequence[str] | type[enum.Enum],
                 default: str | None = None, **kw: Any):
        if isinstance(choices, type) and issubclass(choices, enum.Enum):
            values = [c.value for c in choices]
        else:
            values = list(choices)
        if not values:
            raise ValueError("EnumParam needs at least one choice")
        super().__init__(label, default=default if default is not None else values[0], **kw)
        self.choices = values

    def validate(self, value: Any) -> str:
        if isinstance(value, enum.Enum):
            value = value.value
        if value not in self.choices:
            raise ParamError(
                f"{self.name}: {value!r} not one of {self.choices}"
            )
        return value


class StringParam(ParamSpec):
    widget_hint = "line_edit"

    def __init__(self, label: str, *, default: str = "", **kw: Any):
        super().__init__(label, default=default, **kw)

    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ParamError(f"{self.name}: expected str, got {type(value).__name__}")
        return value


class PathParam(StringParam):
    """File/dir path stored as a string; resolved against the workflow base
    directory at execution time (docs/06 §1 — workflow-relative assets)."""

    widget_hint = "path_picker"

    def __init__(self, label: str, *, default: str = "", mode: str = "open",
                 filter: str = "", **kw: Any):
        super().__init__(label, default=default, **kw)
        if mode not in ("open", "save", "dir"):
            raise ValueError(f"PathParam mode must be open/save/dir, got {mode!r}")
        self.mode = mode
        self.filter = filter


def default_params(specs: Sequence[ParamSpec]) -> dict[str, Any]:
    return {s.name: s.default for s in specs}


def validate_params(
    specs: Sequence[ParamSpec], values: dict[str, Any]
) -> dict[str, Any]:
    """Validate a full value dict against specs; unknown names raise."""
    by_name: dict[str, ParamSpec] = {s.name: s for s in specs}
    out: dict[str, Any] = default_params(specs)
    for key, value in values.items():
        spec = by_name.get(key)
        if spec is None:
            raise ParamError(f"unknown parameter {key!r} (known: {sorted(by_name)})")
        out[key] = spec.validate(value)
    return out


ParamFactory = Callable[..., ParamSpec]
