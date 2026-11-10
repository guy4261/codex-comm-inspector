"""Short hover explanations and their Tkinter bindings."""

import tkinter as tk
from tkinter import ttk

EXPLANATIONS = {
    "pane_divider": "Drag to resize the panes.",
    # Inspector controls, record columns, and filter dialogs.
    "inspector.choose_home": "Choose the Codex data folder to search for saved sessions.",
    "inspector.refresh": "Rescan local Codex sessions and traces, and reload the selected local source.",
    "inspector.open_files": "Open saved captures, exports, Codex logs, or trace files.",
    "inspector.source_filter": "Type part of a conversation title, project name, or filename to narrow the list.",
    "inspector.sources": "Select a local session, trace, or imported source to view its records.",
    "inspector.analyze_trace": "Inspect the model calls, context, and tool results in the selected Codex trace.",
    "inspector.coverage": "Shows what the selected source captured and where it came from.",
    "inspector.record_query": "Search record types, summaries, and full payloads. Press Enter to find matches.",
    "inspector.find": "Show records that match the search text and selected filters.",
    "inspector.clear": "Clear the record search and all record filters.",
    "inspector.filter.kind": "Choose which record types to show.",
    "inspector.filter.direction": "Choose which traffic directions or roles to show.",
    "inspector.filter.focus_points": "Show only records with detected user text or assistant replies in their unexpanded payloads.",
    "inspector.records": "Select a row to inspect its payload. Press Ctrl+C to copy selected rows as a Markdown table.",
    "inspector.column.time": "Timestamp from the source, when available. Click to sort.",
    "inspector.column.direction": "How the record relates to the exchange, such as sent, received, or local. Click to sort.",
    "inspector.column.kind": "Message, event, or payload type. Click to sort.",
    "inspector.column.focus_points": "Places the arrow can jump to in the unexpanded payload. Each place counts once. Click to sort.",
    "inspector.column.user_texts": "Text occurrences identified as user text in the unexpanded payload. Click to sort.",
    "inspector.column.replies": "Text occurrences identified as assistant replies in the unexpanded payload. Click to sort.",
    "inspector.column.summary": "Short description of the record. Click to sort.",
    "inspector.column.tokens": "Estimated token count for the full saved record, including JSON syntax. Click to sort.",
    "inspector.column.usage": "Total token usage reported in the record, when available. Click to sort.",
    "inspector.column.cached": "Percentage of reported input tokens served from cache. Click to sort.",
    "inspector.payload": "Shows the selected record. Detected user text is red and assistant replies are green.",
    "inspector.pretty": "Indent valid JSON to make it easier to read.",
    "inspector.drilldown": "Expand JSON objects stored as strings, mark expanded field names in purple, and show line breaks in string values.",
    "inspector.drilldown.no_record": "Select a record to check whether Drilldown can expand its payload or show line breaks.",
    "inspector.drilldown.no_objects": "This payload has no JSON objects stored as strings or multiline string values.",
    "inspector.drilldown.unreadable": "Drilldown needs a readable JSON payload. This payload could not be parsed as JSON.",
    "inspector.drilldown.too_deep": "This JSON payload is nested too deeply for Drilldown to process.",
    "inspector.wrap": "Wrap long lines to fit the payload pane.",
    "inspector.copy_payload": "Copy the saved payload before display formatting.",
    "inspector.tokenization": "Toggle token colors in the payload and show a local token estimate.",
    "inspector.token_status": "Shows the local token estimate and tokenizer. With Drilldown on, it counts text before expansion.",
    "inspector.focus_text": "Jump to the next detected user message or assistant reply in the payload.",
    "inspector.focus_text.disabled": "This payload view has no detected user messages or assistant replies to jump to.",
    "inspector.status": "Shows progress, matching record counts, copy confirmations, and errors.",
    "inspector.filter.options": "Click values to include or exclude them. Apply uses the highlighted values.",
    "inspector.filter.all": "Select every value so this filter allows all records.",
    "inspector.filter.none": "Deselect every value so this filter hides all records.",
    "inspector.filter.apply": "Apply the selected values and update the records table.",
    # Trace analyzer controls, tabs, and table columns.
    "trace.source_title": "Name of the selected trace.",
    "trace.status": "Shows analysis progress, trace totals, and clipboard confirmations.",
    "trace.model_calls": "Select a model call to inspect its payloads, request context, and tool results.",
    "trace.request_event": "Event sequence number of the captured model request.",
    "trace.call_id": "Identifier that groups the request, response, and related events for a model call.",
    "trace.snapshot": "A full request, a delta that references an earlier response, or an unavailable request.",
    "trace.input": "Total input tokens reported for the call, including cached input.",
    "trace.cached_input": "Input tokens the service reported as served from the prompt cache.",
    "trace.uncached_input": "Input tokens outside the cache, derived from total minus cached input when needed.",
    "trace.output": "Output tokens reported for the call, which may include reasoning tokens.",
    "trace.reasoning": "Reasoning tokens reported separately when the capture includes them.",
    "trace.copy_usage": "Copy the selected call’s reported token usage and trace reference as a Markdown table.",
    "trace.call_details": "Shows the selected call’s model, status, collapsed duplicates, and previous response ID when available.",
    "trace.payloads_tab": "Browse saved request, response, and tool payloads for the selected call.",
    "trace.context_tab": "Compare decoded text in this request with the previous captured request on the same thread.",
    "trace.tools_tab": "Review tool diagnostics and compare emitted results with excerpts included in model requests.",
    "trace.payload_sizes": "Payload sizes include formatting and trace fields from the saved file.",
    "trace.event": "Sequence number of the associated event in the trace.",
    "trace.payload_type": "Type assigned to the saved payload by the trace recorder.",
    "trace.lifecycle": "Recorded event that produced the payload, such as a request, response, or tool event.",
    "trace.reference": "Path of the saved payload file relative to the trace directory.",
    "trace.bytes": "Size of the saved payload file in bytes.",
    "trace.payload_characters": "Number of characters in the saved payload text after UTF-8 decoding.",
    "trace.context_note": "Shows the request snapshot, which request it’s compared with, and how it’s counted.",
    "trace.context_source": "Category of decoded request text, such as instructions, tool schemas, or history.",
    "trace.context_characters": "Total decoded Unicode characters for this source.",
    "trace.context_tokens": "Locally counted tokens for decoded text in this source.",
    "trace.new_characters": "Characters in segments without a matching occurrence in the previous captured request.",
    "trace.new_tokens": "Locally counted tokens in segments without a matching occurrence in the previous captured request.",
    "trace.repeated_characters": "Characters in segments with a matching occurrence in the previous captured request.",
    "trace.repeated_tokens": "Locally counted tokens in segments with a matching occurrence in the previous captured request.",
    "trace.all_tools": "Include tool results from the entire trace instead of just the selected model call.",
    "trace.tool": "Name of the tool that ran.",
    "trace.tool_status": "Recorded outcome of the tool execution.",
    "trace.diagnostics": "Flags possible issues such as broad searches, truncation, long lines, or retries after failure.",
    "trace.emitted_characters": "Number of characters in the captured output emitted by the tool.",
    "trace.excerpt_characters": "Number of characters in the matching excerpt included in a later model request.",
    "trace.tool_details": "Shows the selected tool call’s identifier and details about any diagnostic flags.",
    "trace.emitted_preview": "Preview of the output captured when the selected tool ran.",
    "trace.excerpt_preview": "Preview of the output in the next matching model request. For nested tools this may show the enclosing code cell’s output.",
    "trace.copy_evidence": "Copy trace references and counts for the selected row as a Markdown table.",
    "trace.copyable_rows": "Select a row and press Ctrl+C to copy its evidence as a Markdown table.",
    "trace.tool_rows": "Select a tool result to compare its captured output with the excerpt included in a model request.",
}

_TRACE_TYPES = {
    "rollout_started": "Marks the start of the traced Codex rollout and identifies its root thread.",
    "rollout_ended": "Marks the end of the traced rollout and records its outcome.",
    "recording_completed": "The recorder finished writing the trace bundle.",
    "thread_started": "A Codex thread started within the rollout.",
    "thread_ended": "A Codex thread ended and recorded its outcome.",
    "thread_resumed": "Codex reloaded a thread that was already part of this trace.",
    "codex_turn_started": "A turn began in the recorded Codex thread.",
    "codex_turn_ended": "A turn ended in the recorded Codex thread.",
    "history_item_accepted": "Codex accepted an item into conversation history.",
    "inference_started": "Codex began an attempt to call the model.",
    "inference_completed": "The model request attempt finished and recorded a response.",
    "inference_failed": "The model request attempt failed. A partial response may be saved.",
    "inference_cancelled": "Codex stopped reading the model response before it finished.",
    "tool_call_started": "Codex began dispatching a tool call.",
    "tool_call_ended": "The tool call ended and recorded its outcome and any result.",
    "tool_call_runtime_started": "Records how a tool started executing.",
    "tool_call_runtime_ended": "Records how a tool finished executing.",
    "code_cell_started": "Codex began running a JavaScript code cell.",
    "code_cell_initial_response": "The code cell returned its first response. Work may still be running.",
    "code_cell_ended": "The code cell finished and recorded its final status.",
    "protocol_event_observed": "The trace captured a Codex UI or protocol event.",
    "mcp_tool_call_correlation_assigned": "Links a Codex tool call to its execution in an MCP backend.",
    "stdin_target_resolved": "Codex identified the running command that would receive input.",
    "agent_result_observed": "A child agent’s completion was delivered to its parent thread.",
    "compaction_started": "Codex began reducing the conversation history for later model calls.",
    "compaction_request_started": "Codex began a request to reduce conversation history.",
    "compaction_request_completed": "The context compaction request returned a result.",
    "compaction_request_failed": "The context compaction request failed.",
    "compaction_installed": "Codex applied the compacted conversation history.",
    "inference_request": "A saved model request snapshot, including available inputs, tools, and settings.",
    "inference_response": "A saved model response or a summary of its streamed output.",
    "compaction_request": "Saved input for a request to reduce conversation history.",
    "compaction_response": "Saved result of a context compaction request.",
    "compaction_checkpoint": "Saved snapshot of replacement history installed by compaction.",
    "tool_invocation": "The tool request and its arguments as recorded by Codex.",
    "tool_result": "The result returned by a tool to its caller.",
    "tool_runtime_event": "An observation about how a tool executed, such as its start or finish.",
    "terminal_runtime_event": "A recorded terminal action or piece of terminal output.",
    "protocol_event": "Saved contents of a Codex UI or protocol event.",
    "session_metadata": "Metadata captured when a Codex session or thread started.",
    "agent_result": "Saved notification delivered when a child agent reported back.",
    "trace manifest": "Identifies the trace and describes its bundle.",
    "trace event": "A trace event with no more specific type label.",
    "trace payload": "A saved trace payload with no more specific type label.",
    "unparsed trace event": "This trace line could not be read as JSON.",
    "trace value": "This trace line contains JSON without an event object.",
    "unavailable trace payload": "The trace refers to a payload file that could not be opened.",
}

_SESSION_EVENTS = {
    "item_started": "Codex recorded that a turn item began.",
    "item_completed": "Codex recorded that a turn item finished.",
    "token_count": "A usage update that may include cumulative totals or the latest call’s counts.",
    "task_started": "A Codex turn began.",
    "turn_started": "A Codex turn began.",
    "task_complete": "A Codex turn finished.",
    "turn_complete": "A Codex turn finished.",
    "thread_settings_applied": "Codex applied settings to this thread.",
    "turn_aborted": "The turn was interrupted or cancelled.",
    "user_message": "Codex recorded a user message event in the session.",
    "agent_message": "Codex recorded an assistant message event in the session.",
}

_MESSAGE_ROLES = {
    "user": "A message recorded with the user role.",
    "assistant": "A message recorded with the assistant role.",
    "system": "Instructions or context recorded with the system role.",
    "developer": "Instructions or context recorded with the developer role.",
    "tool": "A message recorded as a tool result.",
    "function": "A message recorded as a function result.",
}

_ITEM_TYPES = {
    "message": "A message item attributed to its recorded role.",
    "reasoning": "A reasoning item that can carry a summary or encrypted context for a later request.",
    "function_call": "The model requested a named function with arguments.",
    "function_call_output": "The function result associated with a model tool call.",
    "custom_tool_call": "The model requested a custom tool with free-form input.",
    "custom_tool_call_output": "The result associated with a custom tool call.",
    "web_search_call": "A call to the built-in web search tool.",
    "file_search_call": "A search through indexed files.",
    "code_interpreter_call": "A request to execute code in the Code Interpreter environment.",
    "computer_call": "A request to perform computer actions.",
    "computer_call_output": "The result returned after carrying out computer actions.",
    "image_generation_call": "A request to generate or edit an image.",
    "mcp_call": "A call to a tool exposed by an MCP server.",
    "mcp_list_tools": "The tools listed by an MCP server.",
    "mcp_approval_request": "A request to approve an MCP tool call.",
    "mcp_approval_response": "The approval or rejection of an MCP tool call.",
    "shell_call": "A request to run shell commands.",
    "shell_call_output": "The output and execution outcome of a shell call.",
    "apply_patch_call": "A file patch requested by the model.",
    "apply_patch_call_output": "The result of applying a requested patch.",
    "compaction": "Compressed context for later model requests, which can be stored in encrypted form.",
    "agent_message": "A message passed between Codex agents.",
    "additional_tools": "Additional tool definitions supplied to the model.",
    "configuration_update": "A configuration update saved in Codex conversation history.",
}

_RECORD_TYPES = {
    "session_meta": "Identifies the saved Codex session and records its startup metadata.",
    "turn_context": "Settings and environment context saved for a Codex turn.",
    "world_state": "A snapshot or update of context Codex tracks, such as the environment or available tools.",
    "token_usage_record": "Token usage recorded for a model response.",
    "inter_agent_communication_metadata": "Records how a message between agents was delivered.",
    "compacted": "A saved checkpoint used to reconstruct conversation history after compaction.",
    "unparsed JSONL": "This line contains incomplete or invalid JSON.",
    "JSONL value": "This line contains a JSON value other than an object.",
    "JSONL object": "This line contains a JSON object without a record type.",
    "conversation": "An exported conversation or its metadata.",
    "node": "An entry in the exported conversation graph with no recorded author role.",
    "HAR metadata": "Information about the HTTP archive apart from the captured exchanges.",
    "HTTP exchange": "A captured browser request and its response stored together.",
    "API request": "A saved API request with a model and input or messages.",
    "API metadata": "Metadata from the enclosing API response or list.",
    "Preview metadata": "Information about a locally assembled Codex prompt preview.",
    "JSON": "Imported JSON without a named type or object label.",
    "SSE": "A block from a server-sent event stream without a named event type.",
    "response.created": "The API created a response and began its lifecycle.",
    "response.in_progress": "The API is processing the response.",
    "response.completed": "The API finished generating the response.",
    "response.failed": "The response ended with an error.",
    "response.incomplete": "The response stopped before it finished.",
    "response.output_item.added": "An item was added to the response output.",
    "response.output_item.done": "An item in the response output finished.",
    "response.content_part.added": "A piece of content was added within an output item.",
    "response.content_part.done": "A piece of content within an output item was finalized.",
    "response.output_text.delta": "A fragment of generated text arrived.",
    "response.output_text.done": "This event contains the final text for this part of the response.",
    "response.function_call_arguments.delta": "A fragment of the arguments for a function call arrived.",
    "response.function_call_arguments.done": "The arguments for a function call are complete.",
    "response.refusal.delta": "A fragment of the refusal text arrived.",
    "response.refusal.done": "The refusal text for this part of the response is complete.",
}

_TABLE_VALUES = {
    "inspector.column.direction": {
        "input": "Labeled as model input based on the saved record’s type or role.",
        "output": "Labeled as model output based on the saved record’s type or role.",
        "local": "Stored as a local Codex record, such as a lifecycle event or tool record.",
        "sent": "An outgoing message or request in the imported source.",
        "received": "An incoming message, response item, or stream event in the imported source.",
        "exchange": "A captured request and response stored together.",
        "metadata": "Descriptive information about the source or exchange.",
        "preview": "An input item assembled in a local Codex prompt preview.",
        "": "The Inspector has no direction label for this record.",
    },
    "trace.snapshot": {
        "Full capture": "The saved request has no previous-response reference.",
        "Delta · previous response": "This request refers to an earlier response for context and supplies additional input.",
        "Request unavailable": "The trace has no readable request snapshot for this call.",
    },
    "trace.payload_type": _TRACE_TYPES,
    "trace.lifecycle": {
        **_TRACE_TYPES,
        "Request": "The selected request snapshot for this call.",
        "Response": "The selected response snapshot for this call.",
        "Other recorded variant": "An additional distinct payload saved for this call.",
    },
    "trace.context_source": {
        "Instructions": "Instruction text included in the captured request.",
        "Skill catalog": "Skill definitions advertised to the model in the request.",
        "Tool schemas": "Definitions of the tools available to the model.",
        "History": "Captured conversation history and older tool results.",
        "Current tool results": "Tool results that appear after the latest user message in the captured request.",
        "Opaque or encoded": "Encrypted or encoded fields counted separately from readable text.",
    },
    "trace.tool": {
        "Tool": "The trace did not provide a name for this tool.",
        "Code cell": "A JavaScript code cell that can run other tools.",
        "functions.exec": "Runs a JavaScript code cell that can call and combine other tools.",
        "exec_command": "Starts a command in a shell.",
        "write_stdin": "Sends input to a running command or checks for more output.",
        "apply_patch": "Applies a patch to workspace files.",
    },
    "trace.tool_status": {
        "completed": "The tool finished execution.",
        "failed": "The tool reported a failure or the analyzer detected a failure signal.",
        "yielded": "The code cell returned control while work could still be running.",
        "cancelled": "The tool execution was cancelled.",
        "": "The trace did not provide a status for this tool execution.",
    },
}

_DIAGNOSTICS = {
    "Large single line": "The output includes a line of at least 3,000 characters.",
    "Broad search": "The analyzer flagged this search as potentially unrestricted.",
    "Truncation": "The saved output shows a truncation marker or appears shortened in the request.",
    "Failed call retried": "A later tool call looks like a retry of an earlier failed call.",
    "—": "The analyzer found no diagnostic flags for this tool result.",
}

_CONTEXT_COMPARISON_MISSING = (
    "No count is available for this comparison. It needs an earlier captured request."
)
_MISSING_VALUES = {
    "inspector.column.time": "No timestamp is available for this record.",
    "inspector.column.tokens": "No local token estimate is available for this record.",
    "inspector.column.usage": "The record has no usable total or pair of input and output token counts.",
    "inspector.column.cached": "This needs valid cached and total input counts, with a nonzero input count.",
    "trace.request_event": "The trace has no request event number for this call.",
    "trace.input": "The trace has no reported input token count for this call.",
    "trace.cached_input": "The trace has no reported cached input count for this call.",
    "trace.uncached_input": "The uncached count was neither reported nor available from the other input counts.",
    "trace.output": "The trace has no reported output token count for this call.",
    "trace.reasoning": "The trace has no separately reported reasoning token count for this call.",
    "trace.event": "The trace has no event number for this row.",
    "trace.reference": "The trace has no saved payload path for this row.",
    "trace.context_tokens": "A local token count is unavailable for this context source.",
    "trace.new_characters": _CONTEXT_COMPARISON_MISSING,
    "trace.repeated_characters": _CONTEXT_COMPARISON_MISSING,
    "trace.new_tokens": "This comparison needs an earlier request and a local token count.",
    "trace.repeated_tokens": "This comparison needs an earlier request and a local token count.",
    "trace.emitted_characters": "No emitted text was available to count for this tool result.",
    "trace.excerpt_characters": "No matching excerpt was available to count in a later request.",
}

_INSPECTOR_MEASUREMENTS = {
    "inspector.column.time": "This is the timestamp from the source.",
    "inspector.column.focus_points": "The focus point count for the unexpanded payload is {value}.",
    "inspector.column.user_texts": "The detected user text count for the unexpanded payload is {value}.",
    "inspector.column.replies": "The detected assistant reply count for the unexpanded payload is {value}.",
    "inspector.column.tokens": "The local tokenizer counted {value} tokens in the full saved record, including formatting.",
    "inspector.column.usage": "The record reports {value} total tokens, either explicitly or as input plus output.",
    "inspector.column.cached": "Cached input divided by total input tokens, rounded to {value}.",
}

_TRACE_COLUMN_HELP = {
    "trace.request_event",
    "trace.call_id",
    "trace.input",
    "trace.cached_input",
    "trace.uncached_input",
    "trace.output",
    "trace.reasoning",
    "trace.event",
    "trace.reference",
    "trace.bytes",
    "trace.payload_characters",
    "trace.context_characters",
    "trace.context_tokens",
    "trace.new_characters",
    "trace.new_tokens",
    "trace.repeated_characters",
    "trace.repeated_tokens",
    "trace.emitted_characters",
    "trace.excerpt_characters",
}


def _record_type_text(value):
    kind, _, subtype = value.partition(" / ")
    if kind == "event_msg":
        return _SESSION_EVENTS.get(
            subtype, "A Codex event saved in the session history."
        )
    if kind == "response_item":
        item, _, role = subtype.partition(" / ")
        if item == "message":
            return _MESSAGE_ROLES.get(role, _ITEM_TYPES["message"])
        return _ITEM_TYPES.get(
            item, "An input or output item saved in Codex session history."
        )
    return (
        _TRACE_TYPES.get(value)
        or _RECORD_TYPES.get(value)
        or _ITEM_TYPES.get(value)
        or _MESSAGE_ROLES.get(value)
    )


def _cell_text(column, value):
    if column == "inspector.column.kind":
        return _record_type_text(value)
    if column == "trace.diagnostics":
        return "\n".join(
            _DIAGNOSTICS[flag] for flag in value.split(", ") if flag in _DIAGNOSTICS
        )
    if column in _TABLE_VALUES:
        return _TABLE_VALUES[column].get(value)
    if value in ("", "—"):
        return _MISSING_VALUES.get(column)
    if column in _INSPECTOR_MEASUREMENTS:
        return _INSPECTOR_MEASUREMENTS[column].format(value=value)
    if column in _TRACE_COLUMN_HELP:
        return EXPLANATIONS[column]
    return None


_HOVER_DELAY_MS = 650
_VISIBLE_MS = 5000


def explain(widget, key):
    """Bind a hover explanation by key or by a function that supplies the current key."""
    if callable(key):
        _HoverHelp(widget, lambda x, y: (None, EXPLANATIONS[key()]))
    else:
        text = EXPLANATIONS[key]
        _HoverHelp(widget, lambda x, y: (None, text))
    return widget


def explain_table(tree, headings, *, body=None):
    """Bind help for headers and known cell values by column ID."""
    body_text = EXPLANATIONS[body] if body is not None else None

    def tip_at(x, y):
        region = tree.identify_region(x, y)
        if region not in ("heading", "cell", "tree"):
            return None
        column = tree.column(tree.identify_column(x), "id")
        key = headings.get(column)
        if region == "heading":
            return ((None, column), EXPLANATIONS[key]) if key else None
        item = tree.identify_row(y)
        if not item:
            return None
        if key and region == "cell":
            text = _cell_text(key, str(tree.set(item, column)))
            if text:
                return (item, column), text
        if body_text:
            return (item, None), body_text
        return None

    _HoverHelp(tree, tip_at)


def explain_tabs(notebook, tabs):
    """Bind explanations by the widget used as each notebook tab's content."""
    texts = {str(tab): EXPLANATIONS[key] for tab, key in tabs.items()}

    def tip_at(x, y):
        try:
            index = notebook.index(f"@{x},{y}")
        except tk.TclError:
            return None
        tab = notebook.tabs()[index]
        return (tab, texts[tab]) if tab in texts else None

    _HoverHelp(notebook, tip_at)


def explain_sashes(panes):
    """Explain the draggable dividers between panes."""
    text = EXPLANATIONS["pane_divider"]

    def tip_at(x, y):
        sash = panes.identify(x, y)
        return (sash, text) if sash != "" else None

    _HoverHelp(panes, tip_at)


class _HoverHelp:
    def __init__(self, widget, tip_at):
        self.widget = widget
        self.tip_at = tip_at
        self.tip = None
        self.timer = None
        self.popup = None

        for event in ("<Enter>", "<Motion>"):
            widget.bind(event, self._hover, add="+")
        for event in ("<Leave>", "<Unmap>", "<Destroy>"):
            widget.bind(event, self._reset, add="+")
        for event in ("<ButtonPress>", "<Button-1>", "<MouseWheel>", "<KeyPress>"):
            widget.bind(event, self._hide, add="+")

    def _hover(self, event):
        tip = self.tip_at(event.x, event.y)
        if tip == self.tip:
            return
        self._hide()
        self.tip = tip
        if tip:
            self.timer = self.widget.after(_HOVER_DELAY_MS, self._show)

    def _show(self):
        self.timer = None
        widget = self.widget
        x, y = widget.winfo_pointerxy()
        if widget.winfo_containing(x, y) is not widget or self.tip != self.tip_at(
            x - widget.winfo_rootx(), y - widget.winfo_rooty()
        ):
            self.tip = None
            return
        _, text = self.tip

        popup = self.popup = tk.Toplevel(widget, takefocus=False)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(widget.winfo_toplevel())
        label = ttk.Label(
            popup,
            text=text,
            padding=(7, 4),
            relief="solid",
            justify="left",
            wraplength=310,
        )
        label.pack()
        x_offset, y_offset = 14, 20
        right = widget.winfo_vrootx() + widget.winfo_vrootwidth()
        bottom = widget.winfo_vrooty() + widget.winfo_vrootheight()
        if x < right <= x + x_offset + label.winfo_reqwidth():
            x_offset = -label.winfo_reqwidth() - 8
        if y < bottom <= y + y_offset + label.winfo_reqheight():
            y_offset = -label.winfo_reqheight() - 8
        popup.geometry(f"+{x + x_offset}+{y + y_offset}")
        popup.deiconify()
        # Windows can map a borderless popup behind its owner.
        popup.lift()
        self.timer = widget.after(_VISIBLE_MS, self._expire)

    def _expire(self):
        self.timer = None
        self._hide()

    def _hide(self, _event=None):
        if self.timer is not None:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.popup is not None:
            if self.popup.winfo_exists():
                self.popup.destroy()
            self.popup = None

    def _reset(self, _event):
        self._hide()
        self.tip = None
