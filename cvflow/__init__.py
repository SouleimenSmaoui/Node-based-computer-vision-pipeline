"""CVFlow — visual computer-vision workflow builder.

Layering (enforced by convention, see CLAUDE.md):
    core    -> stdlib, numpy, cv2 only
    engine  -> core
    nodes   -> cvflow.sdk only
    io      -> core
    plugins -> core
    cli     -> everything except app
    app     -> everything (Phase 1, not yet present)
"""

__version__ = "0.1.0"
