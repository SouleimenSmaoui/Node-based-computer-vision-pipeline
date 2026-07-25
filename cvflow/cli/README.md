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

`--set` accepts every param type, including the tuple-valued ones — each spec parses
its own text (`ParamSpec.parse`), so there is no type-handling here to keep in sync:

```
--set blur.kernel=9              # int
--set crop.rect=8,8,320,240      # rect: x,y,w,h
--set filter.area=100,5000       # range: low,high  (or 100:5000)
--set text.color=0,255,0         # colour: B,G,R — OpenCV order, not RGB
```

A param editable only in the GUI would quietly break CLI parity (docs/01 §3), so a
new `ParamSpec` needs a `parse()` and a `tests/test_cli.py` case, not just a widget.

Next here: `--batch` over folders (Phase 2, with the streaming engine), `--json`
report output for CI consumption, `cvflow plugin new` (Phase 2).
