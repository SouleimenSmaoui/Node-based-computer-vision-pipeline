# cvflow.plugins — node discovery

`loader.py` builds the `NodeRegistry` from:
1. **Built-in packs** — walks `cvflow.nodes.*` and registers every `@node` class.
2. **Installed packages** — pip entry points, group `cvflow.nodes`
   (see `pyproject.toml` for the worked example external plugins copy).

`builtin_registry()` is the cached one-call entry the CLI (and later the GUI) uses.

Failure isolation: a module that raises on import becomes a `PluginFailure` record
(source, error, traceback) — startup never dies because of a broken plugin (N8).
The CLI prints these as warnings; the GUI will get a Plugins panel.

Next here (Phase 2 — docs/04 §2): user plugins folder (`~/.cvflow/plugins` +
per-project `cvflow_plugins/`) with reload support; `cvflow plugin new` scaffold.
