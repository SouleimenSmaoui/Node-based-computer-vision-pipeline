# CODE_REVIEW.md — actionable review findings (2026-07-08)

> **Audience:** an AI (or human) session tasked with fixing these findings.
> **Scope reviewed:** Phase 0 core/engine + Phase 1 GUI (`cvflow/app/`) + node packs, at 80 tests green.
>
> **Ground rules for whoever fixes this (from CLAUDE.md — they are binding):**
> - Run `.venv\Scripts\python.exe -m pytest` before and after every fix; the suite **must stay green** (80 tests, includes offscreen GUI smoke tests).
> - GUI tests run with `QT_QPA_PLATFORM=offscreen`. **Never let a modal dialog open in a headless test** (e.g. the "discard changes?" `QMessageBox`) — it blocks forever. `tests/test_app_smoke.py` shows the `mark_clean()` pattern.
> - Respect import layering: `core` → stdlib/numpy/cv2 only; `engine` → `core`; nodes → `cvflow.sdk` only; **only `cvflow/app/` imports Qt**.
> - After the fixes: update STATUS.md ("Known weak spots" and, where relevant, deviations), and the README of any package touched.
> - Each fix in §1 needs a regression test.

---

## 1) Critical issues

### 1.1 Cache poisoning: params are read twice per node while the GUI mutates them concurrently — **HIGH, fix first**

**Files:** `cvflow/engine/cache.py:22-38`, `cvflow/engine/executor.py` (`dispatch()` ~line 148-204, `_execute_node()` ~line 333-351, `_config_issue()` ~line 289), `cvflow/app/controllers/execution_controller.py` (`mutate()` docstring).

**Defect.** For each node, the engine reads `inst.params` **twice at different times**:
1. `node_fingerprint(inst, …)` reads `inst.params` live to compute the cache key (`cache.py:29` and again inside `external_state` at `cache.py:34`);
2. `_execute_node()` later builds the `ExecutionContext` with `params=inst.params`, which `Namespace.__init__` copies **at execution time**.

The GUI deliberately mutates params *without* the run-lock (`ExecutionController.mutate` docstring claims param edits are "benign" — **that claim is wrong**, delete/correct it). If a param edit lands between read (1) and read (2):
- the node executes with the **new** value but its outputs are cached under the **old** value's fingerprint (`executor.py`, `complete()` → `self.cache.put(fp, outputs)`);
- the immediate rerun is fine (new fingerprint → miss), **but when the user returns to the old value** (slider back, or **undo**, which the GUI supports), the poisoned entry *hits* and a **wrong image is displayed persistently** until eviction.

The window is µs–ms per node, but interactive tuning generates thousands of runs per session. Low frequency, sticky consequence, silent failure — it directly breaks the product's core promise ("the fingerprint cache is always correct").

**Fix.** One coherent snapshot per node per run: take `params_snap = dict(inst.params)` at the top of `dispatch()`, and use that same snapshot for config validation, the fingerprint, `external_state`, and node execution. See refactored code in §3.1. Keep `node_fingerprint`'s new `params` argument optional so existing callers/tests don't break.

**Regression test (mechanism-level; the race itself isn't deterministically reproducible):**
- assert `node_fingerprint(inst, fps, None, params=snap)` is unaffected by mutating `inst.params` afterwards;
- assert the `ExecutionContext` a node receives contains the values that were snapshotted at dispatch (e.g. a test node that records `dict(ctx.params.keys())`+values into `ctx.state`, driven through `ExecutionService.run` with `workers=0`, with `inst.params` mutated via a graph listener fired mid-run if feasible — otherwise assert the plumbing: `_execute_node` must not touch `inst.params`).

---

### 1.2 Armed ("Run") requests can be silently dropped — **MEDIUM-HIGH**

**File:** `cvflow/app/controllers/execution_controller.py` (`arm_and_run()`, `_loop()`).

**Defect A (write race).** `arm_and_run()` assigns `self._armed = {…}` on the GUI thread **outside** `self._cond`; the worker reads-and-clears `self._armed` **inside** `self._cond`. Interleaving: the worker's `self._armed = set()` can execute *after* the GUI's assignment but *before* the new dirty flag is processed → the next run sees `armed=∅`. Result: the user clicks **Run**, no sink executes, no error is shown.

**Defect B (supersession swallows the arm).** If an armed run is superseded mid-run (slider tick during a save), the arm was already consumed at pickup, the sinks finish `SKIPPED`/`CANCELLED`, the report is discarded (`if not superseded: reportReady.emit(...)`), and the user gets **no feedback** that the export never happened.

**Fix.** (a) Move the `_armed` assignment inside `self._cond` (fold into the launch path). (b) After a superseded run, re-arm exactly the sinks that did **not** reach `NodeStatus.OK`, so the retry run performs the side effect with the newest params. See §3.2.

**Regression test:** with `workers=0`, call `arm_and_run(["save"])`, force a supersession (set `_dirty` under `_cond` from the test between runs / schedule immediately), spin until quiescent, assert the save's `NodeStatus` ends `OK` and the file exists exactly once… if timing proves flaky offscreen, at minimum unit-test that `arm_and_run` publishes `_armed` under `_cond` and that the re-arm set computation returns non-OK sinks.

---

### 1.3 Profiler sorts numerically-formatted strings lexicographically — **CONFIRMED at runtime**

**File:** `cvflow/app/panels/profiler.py` (`update_report()`, ~lines 38-56).

**Defect.** Columns "Last ms", "EMA ms", "% run", "Bytes" store the *formatted string* in `DisplayRole`; `QTableWidgetItem` comparison uses `DisplayRole`, so sorting is lexicographic. Verified on PySide6 6.11: descending sort yields `9.50 → 23.10 → 102.35`. The slowest node lands at the **bottom** of the "slowest first" table — the opposite of the panel's purpose. The `UserRole+1` numeric value currently stored is never consulted by Qt.

**Fix.** Use a `QTableWidgetItem` subclass with `__lt__` comparing the numeric value (keeps the pretty text). See §3.3. Delete the now-pointless `UserRole+1` writes and the `_num()` helper if unused.

**Regression test:** build a `ProfilerPanel`, feed a fake `RunReport` with ms values `[9.5, 102.35, 23.1]`, call `update_report`, assert row 0 is the 102.35 node (offscreen-safe).

---

## 2) Suggestions for improvement

Ordered roughly by value. None break public APIs.

1. **`mutate()` blocks the GUI thread for the duration of the in-flight node** (`execution_controller.py`; engine polls cancellation only *between* nodes, `executor.py` `dispatch()`). Harmless today (all nodes are ms-scale) but becomes a UI freeze the day a slow node (template match, script, big morphology) exists. Action now: correct the over-optimistic comment, add to STATUS.md "Known weak spots". Action later (when slow nodes land): adopt `ctx.is_cancelled()` checkpoints inside long-running nodes, and/or queue structural edits to apply on the worker between runs instead of blocking.

2. **Silent-supersession UX for side effects** (beyond fix 1.2): after a *successful* armed run, show a status-bar confirmation ("saved N sink(s)"); after a re-armed retry, indicate it. Small `MainWindow._on_report` change reading sink statuses.

3. **Viewer shows a stale image under geometry overlays** (`cvflow/app/viewer/image_view.py`, `show_output()`): when a viewer is switched to a node whose output is a `ContourSet`, `_buf` (the pixels) remains from the previously viewed node while the header claims the contours node. Either clear the image, or label it honestly ("contours over <previous node label>"). Contours-over-source is useful; the mislabeling is the bug.

4. **Nondeterministic category colors for third-party categories** (`cvflow/app/theme.py`, `category_color`): uses built-in `hash()`, which is salted per process (`PYTHONHASHSEED`) → plugin categories change color every launch. Replace with a stable digest, e.g. `int.from_bytes(hashlib.blake2b(category.encode(), digest_size=2).digest(), "big") % len(_OKABE_ITO)`.

5. **Deprecated `QMouseEvent` 5-arg constructor in middle-button pan** (`cvflow/app/graphview/view.py`, `mousePressEvent`/`mouseReleaseEvent`): works on 6.11 but emits `DeprecationWarning` per click and will break on a future Qt. Use the modern overload with explicit `localPos`/`scenePos`/`globalPos`, or reimplement pan without synthesizing events (track last pos + `translate`).

6. **`QtLogHandler` accumulates on the `"cvflow"` logger** (`cvflow/app/main_window.py`, `_install_logging`): one handler added per `MainWindow`, never removed → multiple windows (tests do this) stack handlers pointing at possibly-deleted consoles. Remove the handler in `closeEvent`, or guard against double-install.

7. **`cvflow/app/inspector/widgets.py` dead/unsafe code:** the `_WIDGETS` fallback dict maps `"slider"` → `_IntWidget`, so a third-party `ParamSpec` subclass with `widget_hint="slider"` that is not an `IntParam` crashes on `spec.step`. Make the unknown-spec fallback `_StringWidget` unconditionally, and delete the no-op `spec.filter.replace(" ", " ")` in `_PathWidget._browse`.

8. **`Resize` violates the BINARY convention** (`cvflow/nodes/geometry/resize.py`): linear/cubic interpolation on a `BINARY` input produces values outside `{0,255}` while the output keeps the `BINARY` space label. Force `INTER_NEAREST` when `image.space is ColorSpace.BINARY`, or emit `GRAY` in that case. Add a node test.

9. **Param-to-pixel latency is estimated, never measured** — the Phase-1 exit criterion is *measured p95 < 100 ms at 1080p*. Add a lightweight probe: timestamp in `InspectorPanel.paramEdited`, carry it through `ExecutionController` (e.g. a monotonically increasing edit-id), log the delta when the viewer's pixmap is set; expose p95 in the status bar or log. Keep it cheap and always-on.

10. **Per-node queued signals will storm the GUI thread at scale** (`EngineHooks → ExecutionController` emits `nodeStatus`/`outputsReady` per node): fine at 11 nodes; docs/05 §6 (N6) requires *batched-per-report* badge/metric updates by ~200 nodes. Note it; don't fix prematurely.

11. **Untested interaction path:** port drag-wiring (`PortItem.mousePressEvent` → `GraphScene.begin_wire/update_wire/finish_wire`) has no automated coverage (offscreen can't synthesize drags well). Add a scene-level unit test calling `begin_wire`/`finish_wire` directly with scene positions over a target port, asserting an edge is created and that incompatible ports emit `connectionRejected`.

12. **Phase-1 exit-criteria gaps** (tracked in STATUS.md Next steps; listed here for completeness): viewer state is written to the workflow `ui` section on save but never restored on open; no autosave / kill-9 recovery; no structural undo (only params/labels); `NodeInstance.disabled` still ignored by engine and GUI.

---

## 3) Refactored code examples

### 3.1 Params snapshot (fixes 1.1)

**`cvflow/engine/cache.py`** — accept an optional pre-taken snapshot; default preserves the old behavior for existing callers:

```python
def node_fingerprint(
    inst: NodeInstance,
    input_fps: list[tuple[str, Any, str]],
    base_dir: str | None,
    params: dict[str, Any] | None = None,
) -> str:
    """``input_fps``: (port_name, upstream fingerprint hex | None, coercion label).

    ``params``: coherent snapshot of the instance's params. Pass the same dict
    to fingerprinting AND execution — reading ``inst.params`` twice at
    different times lets a concurrent GUI edit poison the cache.
    """
    spec = inst.spec
    values = dict(inst.params) if params is None else params
    payload = {
        "t": spec.type_id,
        "v": spec.version,
        "p": {p.name: p.to_json(values.get(p.name)) for p in spec.params},
        "x": spec.node_class.external_state(values, base_dir),
        "i": input_fps,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(blob.encode("utf-8"), digest_size=20).hexdigest()
```

**`cvflow/engine/executor.py`** — take the snapshot once in `dispatch()` and thread it through:

```python
        def dispatch(nid: str) -> None:
            inst = self.graph.nodes[nid]
            node_cls = inst.spec.node_class
            params_snap = dict(inst.params)   # ONE coherent read per node per run

            if token and token.cancelled:
                finalize(nid, NodeMetrics(NodeStatus.CANCELLED))
                return
            if producers[nid] & failed:
                finalize(nid, NodeMetrics(NodeStatus.BLOCKED))
                failed.add(nid)
                return

            issue = self._config_issue(inst, params_snap)
            ...
            fp = node_fingerprint(inst, input_fps, self.resources.base_dir,
                                  params=params_snap)
            ...
            if self._pool_workers() == 0:
                result = _guarded(self._execute_node, nid, inst, input_values,
                                  token, params_snap)
                complete(nid, fp, use_cache, result)
            else:
                fut = self._ensure_pool().submit(
                    _guarded, self._execute_node, nid, inst, input_values,
                    token, params_snap)
                in_flight[fut] = (nid, fp, use_cache)
```

```python
    def _config_issue(self, inst: NodeInstance, params: dict[str, Any]) -> str | None:
        ...
        try:
            issues = self._instance(inst).validate(dict(params))
        ...

    def _execute_node(
        self,
        nid: str,
        inst: NodeInstance,
        input_values: dict[str, Any],
        token: CancellationToken | None,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        node_obj = self._instance(inst)
        ctx = ExecutionContext(
            node_id=nid, spec=inst.spec, inputs=input_values, params=params,
            resources=self.resources, state=self._state.setdefault(nid, {}),
            token=token)
        ...
```

Also **correct the wrong claim** in `ExecutionController.mutate`'s docstring ("Param edits skip the lock: reassigning one `params` value is benign…") — after this fix the true statement is: *param edits skip the lock because each node reads a single coherent snapshot; a mid-run edit can at worst waste one superseded run, never corrupt the cache.*

### 3.2 Armed-run publication + re-arm on supersession (fixes 1.2)

**`cvflow/app/controllers/execution_controller.py`:**

```python
    def arm_and_run(self, sink_ids: Iterable[str]) -> None:
        """Arm side-effect nodes for exactly the next run (Run button)."""
        with self._cond:
            self._armed = {n for n in sink_ids if n in self.graph.nodes}
            self._dirty = True
            if self._token is not None:
                self._token.cancel()      # supersede any in-flight run
            self._cond.notify()
```

```python
            # in _loop(), after service.run(...) returns:
            with self._cond:
                superseded = self._dirty
                if superseded and armed:
                    # Carry the arm forward for sinks that did not complete, so a
                    # slider tick during a save can't silently swallow the export.
                    from cvflow.engine.profiling import NodeStatus
                    not_done = {n for n in armed
                                if (m := report.nodes.get(n)) is None
                                or m.status is not NodeStatus.OK}
                    self._armed |= not_done
            if not superseded:
                self.reportReady.emit(report)
```

(Move the `NodeStatus` import to module level in the real change.)

### 3.3 Numeric profiler sorting (fixes 1.3)

**`cvflow/app/panels/profiler.py`:**

```python
class _NumericItem(QtWidgets.QTableWidgetItem):
    """Displays formatted text but sorts by the underlying number."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self._value = value

    def __lt__(self, other: QtWidgets.QTableWidgetItem) -> bool:
        if isinstance(other, _NumericItem):
            return self._value < other._value
        return super().__lt__(other)
```

```python
        # in update_report(), for columns 2 (Last ms), 3 (EMA), 4 (%), 6 (Bytes):
        numeric = {2: m.ms, 3: m.ema_ms or 0.0, 4: pct, 6: float(m.out_bytes)}
        for c, text in enumerate(values):
            if c in numeric:
                item = _NumericItem(text, numeric[c])
            else:
                item = QtWidgets.QTableWidgetItem(text)
            if c == 0:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, nid)
            self.setItem(r, c, item)
```

### 3.4 Stable category colors (fixes §2.4 — one-liner shown for completeness)

**`cvflow/app/theme.py`:**

```python
import hashlib

def category_color(category: str) -> QtGui.QColor:
    hexv = _CATEGORY_COLORS.get(category)
    if hexv is None:
        idx = int.from_bytes(
            hashlib.blake2b(category.encode("utf-8"), digest_size=2).digest(),
            "big") % len(_OKABE_ITO)
        hexv = _OKABE_ITO[idx]
    return QtGui.QColor(hexv)
```

---

## Definition of done for this review

- [x] §1.1, §1.2, §1.3 fixed, each with a regression test; full suite green.
      *(2026-07-25 — 87 tests, was 80. Commits: `b49f022` §1.1, plus §1.2/§1.3.
      All 7 new tests were run against the pre-fix code first and confirmed
      failing, so they guard the regression rather than describe the fix.
      §1.3 reproduced exactly as reported: descending sort gave
      `fast, middle, slowest`.)*
- [x] §2 items 4–8 fixed (small, low-risk) or explicitly deferred with a STATUS.md note.
      *(2026-07-25 — 91 tests, was 87. §2.5 reimplements the pan by scrolling
      directly instead of using the modern QMouseEvent overload: synthesizing
      events at all was the fragile part, since it also leaned on
      ScrollHandDrag's internals. It is the one fix with no test — synthesizing
      the gesture is precisely what it removes. §2.7's `_WIDGETS` table is
      deleted outright rather than re-pointed, since type dispatch already
      covered every real case.)*
- [x] §2 items 1–3, 9–12 triaged into STATUS.md "Next steps" / "Known weak spots".
      *§2.1, §2.10, §2.11 → "Known weak spots" (§2.1's over-optimistic comment
      corrected; it lived in the module docstring, not `mutate()`'s). §2.2, §2.3
      → "Next steps" item 2. §2.12 was already tracked there.*
- [x] **§2.9 implemented, not just triaged** — `cvflow/app/latency.py`, both ends
      on the GUI thread so the debounce and signal delivery are inside the
      number. **Measured 1080p: p50 38 ms, p95 48 ms, max 53 ms** vs the 100 ms
      budget. This moves a docs/08 Phase-1 exit criterion from *estimated* to
      *measured*; still offscreen, so re-confirm on a real display.
- [x] STATUS.md + touched package READMEs updated (owner's standing documentation duty).
      *`cvflow/engine/README.md` (params-snapshot invariant),
      `cvflow/app/README.md` (threading rules the interactive loop depends on).*
