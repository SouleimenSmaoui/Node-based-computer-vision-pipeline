"""Display Text — format a measured number into a caption."""

from __future__ import annotations

from cvflow.sdk import NumberIn, Node, StringParam, TextIn, TextOut, node


@node(
    id="cvflow.util.display_text",
    version="1.0",
    category="Misc",
    label="Display Text",
    doc="Formats a number into text for Draw Text, so a measurement can be "
        "burned into the image it came from. The template uses Python's format "
        "syntax: '{:.2f} mm' or 'count: {:.0f}'. Wire the Text input instead "
        "to pass a string through a template.",
    keywords=("text", "format", "label", "number", "readout", "display"),
)
class DisplayText(Node):
    value = NumberIn("Value", optional=True)
    text_in = TextIn("Text", optional=True)
    out = TextOut("Text")

    template = StringParam("Template", default="{:.2f}",
                           tooltip="Python format string. '{}' is the incoming "
                                   "value; literal text around it is kept.")

    def process(self, ctx) -> None:
        supplied = ctx.inputs.text_in
        value = supplied if supplied is not None else ctx.inputs.value
        template = ctx.params.template

        if value is None:
            ctx.outputs.out = template
            return
        try:
            ctx.outputs.out = template.format(value)
        except (ValueError, KeyError, IndexError) as exc:
            # A bad template is a typo, not a crash — say which template and
            # what it received, since both are invisible in the graph.
            raise ValueError(
                f"template {template!r} cannot format {value!r}: {exc}") from exc
