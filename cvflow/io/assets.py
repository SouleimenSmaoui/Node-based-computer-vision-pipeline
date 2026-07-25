"""Workflow-relative asset paths (docs/06 §1).

Paths in parameters are stored as written; at execution time nodes resolve
them against the workflow's base directory, so a workflow folder can be
copied, cloned, or committed and still run.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_path(base_dir: str | os.PathLike | None, raw: str) -> Path:
    p = Path(os.path.expandvars(raw)).expanduser()
    if p.is_absolute() or base_dir is None:
        return p
    return (Path(base_dir) / p).resolve()


def make_relative(path: str | os.PathLike, base_dir: str | os.PathLike) -> str:
    """Relative form if the path lives under (or near) base_dir, else absolute."""
    p, base = Path(path).resolve(), Path(base_dir).resolve()
    try:
        return os.path.relpath(p, base)
    except ValueError:  # different drive on Windows
        return str(p)
