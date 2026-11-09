"""Build copyable, content-free evidence from local Codex traces."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from token_counts import token_counter


@dataclass(frozen=True)
class Evidence:
    trace_id: str
    sequence: int
    reference: str
    finding: str
    method: str
    counts: tuple[tuple[str, int | None], ...]
    related_payloads: tuple[str, ...] = ()


def evidence_for(payload, finding, method, counts, *related):
    return Evidence(
        payload.trace_id,
        payload.sequence,
        payload.path or payload.raw_payload_id,
        finding,
        method,
        tuple(counts),
        tuple(
            f"{label} #{other.sequence} · {other.path or other.raw_payload_id}"
            for label, other in related
            if other is not None
        ),
    )


def markdown_evidence(rows):
    def row(values):
        cells = [
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("`", "&#96;")
            .replace("\r\n", "<br>")
            .replace("\r", "<br>")
            .replace("\n", "<br>")
            for value in values
        ]
        return "| " + " | ".join(cells) + " |"

    output = [
        row(
            (
                "Trace ID",
                "Event sequence",
                "Payload reference",
                "Finding",
                "Count method",
                "Counts",
                "Related payloads",
            )
        ),
        row(["---"] * 7),
    ]
    for item in rows:
        counts = ", ".join(
            f"{label}={value:,}" for label, value in item.counts if value is not None
        )
        output.append(
            row(
                (
                    item.trace_id,
                    item.sequence,
                    item.reference,
                    item.finding,
                    item.method,
                    counts or "—",
                    "\n".join(item.related_payloads) or "—",
                )
            )
        )
    return "\n".join(output)


def usage_evidence(call):
    return evidence_for(
        call.response,
        "Reported model usage",
        "Service-reported tokens, uncached derived when absent",
        (
            ("input", call.usage.input_tokens),
            ("cached input", call.usage.cached_input_tokens),
            ("uncached input", call.usage.uncached_input_tokens),
            ("output", call.usage.output_tokens),
            ("reasoning", call.usage.reasoning_tokens),
            ("total", call.usage.total_tokens),
        ),
        ("Request", call.request),
    )


def raw_evidence(payload):
    label = payload.kind
    if isinstance(payload.document, dict) and payload.document.get(
        "previous_response_id"
    ):
        label += " (delta)"
    return evidence_for(
        payload,
        label,
        "Saved payload size",
        (
            ("bytes", payload.raw_bytes),
            ("Unicode characters", payload.raw_chars),
        ),
    )


def previous_requests(calls):
    """Find the preceding captured request on each thread, including across turns."""
    previous = {}
    latest = {}
    for call in calls:
        if call.request is None or not isinstance(call.request.document, dict):
            continue
        thread = call.thread_id
        if thread:
            previous[call.call_id] = latest.get(thread)
            latest[thread] = call
    return previous


def request_context(call, previous, use_tokens=True):
    from trace_context import context_breakdown

    encoding, count = (
        token_counter(call.model) if use_tokens else ("Unicode characters", None)
    )
    baseline = previous.request.document if previous else None
    return encoding, context_breakdown(call.request.document, baseline, count)


def context_evidence(call, previous, encoding, row):
    method = "Decoded segments, Unicode characters"
    if row.tokens is not None:
        method += f" and local {encoding} tokens"
    if call.delta:
        method += ", captured delta fields"
    if row.source == "Tool schemas":
        method += ", schemas in compact JSON"
    return evidence_for(
        call.request,
        row.source,
        method,
        (
            ("characters", row.chars),
            ("tokens", row.tokens),
            ("new characters", row.new_chars),
            ("new tokens", row.new_tokens),
            ("repeated characters", row.repeated_chars),
            ("repeated tokens", row.repeated_tokens),
        ),
        ("Previous request", previous.request if previous else None),
    )


def tool_evidence(tool, flag=None):
    payload = tool.emitted_payload or tool.request_payload
    if payload is None:
        return None
    finding = flag.kind if flag else "Tool result comparison"
    method = "Decoded tool text, Unicode characters"
    if tool.excerpt_scope == "containing code cell":
        method += ", excerpt from enclosing code cell"
    return evidence_for(
        payload,
        finding,
        method,
        (
            (
                "emitted characters",
                len(tool.emitted_text) if tool.emitted_text is not None else None,
            ),
            (
                "longest emitted line",
                tool.longest_line_chars if tool.emitted_text is not None else None,
            ),
            (
                "request excerpt characters",
                len(tool.excerpt_text) if tool.excerpt_text is not None else None,
            ),
        ),
        ("Request excerpt", tool.request_payload if tool.emitted_payload else None),
        (
            "Retry" if finding == "Failed call retried" else "Runtime output",
            flag.related_payload if flag else None,
        ),
    )


def read_analysis(path):
    from trace_calls import load_trace_analysis
    from trace_diagnostics import diagnose_tools

    analysis = load_trace_analysis(path)
    return analysis, diagnose_tools(analysis.events)


def top_findings(analysis, tools, limit, use_tokens=False):
    previous = previous_requests(analysis.calls)
    diagnostics = []
    for tool in tools:
        for flag in tool.flags:
            row = tool_evidence(tool, flag)
            if row is not None:
                diagnostics.append((len(tool.emitted_text or ""), row))

    context = []
    raw_sizes = []
    reported = []
    for call in analysis.calls:
        if call.response is not None:
            usage = usage_evidence(call)
            if any(value is not None for _, value in usage.counts):
                score = (
                    call.usage.input_tokens
                    or call.usage.total_tokens
                    or call.usage.output_tokens
                    or 0
                )
                reported.append((score, usage))
        if call.request is None:
            continue
        if call.request.raw_bytes is not None:
            raw_sizes.append((call.request.raw_bytes, raw_evidence(call.request)))
        if not isinstance(call.request.document, dict):
            continue
        baseline = previous.get(call.call_id)
        encoding, rows = request_context(call, baseline, use_tokens)
        if rows:
            row = rows[0]
            score = row.tokens if row.tokens is not None else row.chars
            context.append((score, context_evidence(call, baseline, encoding, row)))

    # Interleave categories so large requests do not crowd out diagnostics or usage.
    categories = [
        sorted(entries, key=lambda entry: entry[0], reverse=True)
        for entries in (diagnostics, context, reported, raw_sizes)
        if entries
    ]
    for rank in range(min(limit, max(map(len, categories), default=0))):
        for entries in categories:
            if rank < len(entries):
                yield entries[rank][1]
                limit -= 1
                if not limit:
                    return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "trace", type=Path, help="Trace directory, manifest.json or trace.jsonl"
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Maximum evidence rows (default 10)"
    )
    parser.add_argument(
        "--tokens",
        action="store_true",
        help="Estimate decoded context tokens with tiktoken",
    )
    options = parser.parse_args()
    if options.limit < 1:
        parser.error("--limit must be a positive integer")
    path = options.trace / "trace.jsonl" if options.trace.is_dir() else options.trace
    try:
        analysis, tools = read_analysis(path)
        rows = list(top_findings(analysis, tools, options.limit, options.tokens))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Couldn't read trace. {error}\n")
    print(markdown_evidence(rows) if rows else "No evidence rows found in this trace.")


if __name__ == "__main__":
    main()
