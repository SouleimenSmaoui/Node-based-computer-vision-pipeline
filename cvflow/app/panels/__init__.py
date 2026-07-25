"""Bottom panels: console/log, errors, profiler (docs/05 §2.5)."""

from cvflow.app.panels.console import ConsolePanel, ErrorsPanel, QtLogHandler
from cvflow.app.panels.profiler import ProfilerPanel

__all__ = ["ConsolePanel", "ErrorsPanel", "ProfilerPanel", "QtLogHandler"]
