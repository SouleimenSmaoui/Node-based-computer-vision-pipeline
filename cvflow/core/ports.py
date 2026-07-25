"""Port descriptors (docs/04 §1.1).

Declared as class attributes on Node subclasses; collected in declaration
order by ``Node.__init_subclass__`` into the NodeSpec.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cvflow.core.types.base import (
    KIND_ANY,
    KIND_CONTOURS,
    KIND_IMAGE,
    KIND_NUMBER,
    KIND_TEXT,
    PortType,
)
from cvflow.core.types.image import ColorSpace


@dataclass
class PortDecl:
    """Descriptor placed on a Node class body. ``direction`` is 'in'/'out'."""

    direction: str
    label: str
    dtype: PortType
    optional: bool = False
    variadic: bool = False
    same_space_as: str | None = None
    name: str = field(default="", compare=False)

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj, objtype=None) -> "PortDecl":
        return self


def _space(space: ColorSpace | str | None) -> ColorSpace | None:
    if isinstance(space, str):
        return ColorSpace(space)
    return space


# ---- factory functions: the vocabulary node authors use -------------------

def ImageIn(label: str, *, space: ColorSpace | str | None = None,
            optional: bool = False, variadic: bool = False) -> PortDecl:
    return PortDecl("in", label, PortType(KIND_IMAGE, _space(space)),
                    optional=optional, variadic=variadic)


def ImageOut(label: str, *, space: ColorSpace | str | None = None,
             same_space_as: str | None = None) -> PortDecl:
    return PortDecl("out", label, PortType(KIND_IMAGE, _space(space)),
                    same_space_as=same_space_as)


def ContoursIn(label: str, *, optional: bool = False) -> PortDecl:
    return PortDecl("in", label, PortType(KIND_CONTOURS), optional=optional)


def ContoursOut(label: str) -> PortDecl:
    return PortDecl("out", label, PortType(KIND_CONTOURS))


def NumberIn(label: str, *, optional: bool = False) -> PortDecl:
    return PortDecl("in", label, PortType(KIND_NUMBER), optional=optional)


def NumberOut(label: str) -> PortDecl:
    return PortDecl("out", label, PortType(KIND_NUMBER))


def TextIn(label: str, *, optional: bool = False) -> PortDecl:
    return PortDecl("in", label, PortType(KIND_TEXT), optional=optional)


def TextOut(label: str) -> PortDecl:
    return PortDecl("out", label, PortType(KIND_TEXT))


def AnyIn(label: str, *, optional: bool = False, variadic: bool = False) -> PortDecl:
    return PortDecl("in", label, PortType(KIND_ANY), optional=optional, variadic=variadic)


def AnyOut(label: str) -> PortDecl:
    return PortDecl("out", label, PortType(KIND_ANY))
