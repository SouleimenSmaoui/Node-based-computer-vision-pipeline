"""Data types that flow over wires (docs/03).

Public surface re-exported here; node authors get these via ``cvflow.sdk``.
"""

from cvflow.core.types.base import (
    KIND_ANY,
    KIND_CONTOURS,
    KIND_IMAGE,
    KIND_NUMBER,
    KIND_TEXT,
    CheckResult,
    Coerce,
    Ok,
    PortType,
    Reject,
    check_connection,
    nbytes_of,
    summary_of,
)
from cvflow.core.types.image import ColorSpace, ImageBuffer, ValueRange
from cvflow.core.types.geometry import ContourSet

__all__ = [
    "KIND_ANY",
    "KIND_CONTOURS",
    "KIND_IMAGE",
    "KIND_NUMBER",
    "KIND_TEXT",
    "CheckResult",
    "Coerce",
    "Ok",
    "PortType",
    "Reject",
    "check_connection",
    "nbytes_of",
    "summary_of",
    "ColorSpace",
    "ImageBuffer",
    "ValueRange",
    "ContourSet",
]
