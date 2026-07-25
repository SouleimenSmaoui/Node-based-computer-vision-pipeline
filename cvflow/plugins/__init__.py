"""Plugin discovery (docs/04 §2)."""

from cvflow.plugins.loader import PluginFailure, builtin_registry, load_builtin

__all__ = ["PluginFailure", "builtin_registry", "load_builtin"]
