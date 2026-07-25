"""The public node-authoring API (docs/04). Plugins import THIS module only.

Everything re-exported here carries the compatibility promise (semver from
1.0, see docs/01 N10). Internals may move; ``cvflow.sdk`` may not break.

    from cvflow.sdk import (node, Node, ImageIn, ImageOut, IntParam, ...)
"""

from cvflow.core.errors import NodeExecutionError, ParamError
from cvflow.core.node import Issue, Node, NodeSpec, node
from cvflow.core.params import (
    BoolParam,
    CodeParam,
    ColorParam,
    EnumParam,
    FloatParam,
    IntParam,
    ParamSpec,
    PathParam,
    PointParam,
    RangeParam,
    RectParam,
    StringParam,
)
from cvflow.core.ports import (
    AnyIn,
    AnyOut,
    ContoursIn,
    ContoursOut,
    ImageIn,
    ImageOut,
    NumberIn,
    NumberOut,
    TextIn,
    TextOut,
)
from cvflow.core.types import (
    ColorSpace,
    ContourSet,
    ImageBuffer,
    ValueRange,
)
from cvflow.io.assets import resolve_path

__all__ = [
    # node API
    "node", "Node", "NodeSpec", "Issue",
    # ports
    "ImageIn", "ImageOut", "ContoursIn", "ContoursOut",
    "NumberIn", "NumberOut", "TextIn", "TextOut", "AnyIn", "AnyOut",
    # params
    "ParamSpec", "IntParam", "FloatParam", "BoolParam", "EnumParam",
    "StringParam", "PathParam",
    "RangeParam", "PointParam", "RectParam", "ColorParam", "CodeParam",
    # types
    "ImageBuffer", "ColorSpace", "ValueRange", "ContourSet",
    # helpers
    "resolve_path",
    # errors
    "NodeExecutionError", "ParamError",
]
