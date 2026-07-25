# cvflow.cli — headless runner

`main.py` — argparse CLI, console script `cvflow` (see pyproject.toml). The CLI is the
proof the core is headless: it drives the exact `ExecutionService` the GUI will drive.

```
cvflow run <wf.json> [--set NODE.PARAM=VALUE]... [--target NODE_ID]...
                     [--no-sinks] [--profile] [--workers N]
cvflow validate <wf.json>
cvflow nodes list
```

Semantics: side-effect sinks are **armed by default** in `run` (it's a batch
execution, not a preview); `--no-sinks` makes it a dry run; `--target` observes a
node and prints its output summaries. Exit codes: 0 ok, 1 node errors/issues,
2 usage/load errors.

Next here: `--batch` over folders (Phase 2, with the streaming engine), `--json`
report output for CI consumption, `cvflow plugin new` (Phase 2).
