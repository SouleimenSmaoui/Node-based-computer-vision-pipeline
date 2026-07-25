"""cvflow.app — the PySide6 GUI (Phase 1, docs/05).

This is the *only* package permitted to import Qt (hard rule 1, docs/01 §3).
Everything below the GUI stays framework-free; the app drives the same public
engine/graph/registry surface the CLI uses, so nothing here reaches around the
API the headless core already exposes.

Run it with ``python -m cvflow.app [workflow.cvflow.json]`` or the ``cvflow-app``
console script.
"""

from __future__ import annotations

import sys


def run_app(argv: list[str] | None = None) -> int:
    """Create the QApplication, show the main window, enter the event loop."""
    # Imported lazily so ``import cvflow.app`` stays cheap and so a missing
    # PySide6 fails with a clear message instead of at module import time.
    from PySide6 import QtWidgets

    from cvflow.app.main_window import MainWindow
    from cvflow.app.theme import apply_dark_theme

    argv = sys.argv if argv is None else [sys.argv[0] if sys.argv else "cvflow", *argv]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    app.setApplicationName("CVFlow")
    app.setOrganizationName("CVFlow")
    apply_dark_theme(app)

    window = MainWindow()
    window.show()

    # Open a workflow passed on the command line (skip the program name).
    for arg in argv[1:]:
        if arg and not arg.startswith("-"):
            window.open_workflow(arg)
            break

    return app.exec()
