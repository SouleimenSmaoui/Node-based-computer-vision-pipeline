"""Switch — route one of two inputs onward."""

from __future__ import annotations

from cvflow.sdk import AnyIn, AnyOut, BoolParam, Node, node


@node(
    id="cvflow.util.switch",
    version="1.0",
    category="Misc",
    label="Switch",
    doc="Passes either input A or input B through, so two candidate branches "
        "can sit in one graph and be compared by flipping a toggle instead of "
        "rewiring. Note both branches still execute: the engine's demand "
        "closure is computed from the graph's edges, not from this toggle, so "
        "the unselected branch costs its normal run time (its results are "
        "cached, so flipping back and forth is cheap after the first pass).",
    keywords=("switch", "select", "toggle", "route", "ab", "compare", "either"),
)
class Switch(Node):
    a = AnyIn("A", optional=True)
    b = AnyIn("B", optional=True)
    out = AnyOut("Out")

    use_b = BoolParam("Use B", default=False,
                      tooltip="Off passes A through, on passes B.")

    def process(self, ctx) -> None:
        chosen = ctx.inputs.b if ctx.params.use_b else ctx.inputs.a
        which = "B" if ctx.params.use_b else "A"
        ctx.ensure(chosen is not None,
                   f"input {which} is selected but not connected")
        ctx.outputs.out = chosen
