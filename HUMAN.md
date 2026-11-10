Hi! I'm Guy and I used Codex to write this app.

After asking my knowledgable neighbor (thanks Ori!) questions about LLMs, I started wondering what gets sent in every context my Codex is sending on each turn, and whether I should work harder on controlling it (e.g. switch to Pi? honestly idk).

One can literally ask the LLM to answer this question, but I like looking at the data with my own (meaty, fleshy) eyes, so I had it write this tool.

Now I need to figure out what gives. For instance - consider this prompt from yesterday:

> Quick! What's Aerospike? And What's Akka? A paragraph about each one, be terse.

From inspecting the Codex traces, I see it took **27,064** input tokens.
To its defense, **20,736** of them were cached.
With a cold cache, all 27,064 input tokens would have been uncached.

Now. Does the model really need 27k tokens to answer this question? <a href="#appendix-1">[1]</a>

Naturally I immediately asked Codex about that. He thinks ("thinks", whatever) most of it was redundant, and looking at it, I tend to agree.

What can I do now? I'm not really sure. For starters I'll be doing some reading (about
[hooks](https://learn.chatgpt.com/docs/hooks#premodelrequest-and-postmodelrequest),
[`agents.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and
[slash commands](https://learn.chatgpt.com/docs/reference/slash-commands)
) and look at some files -
* `~/.codex/config.toml` (or `/path/to/project/.codex/config.toml`)
* `~/.codex/hooks.json` (or `/path/to/project/.codex/hooks.json`)

but I'm still learning and not sure where this will get me.

In the meanwhile, enjoy this tool or have your agent read this repo and make you one of your own.

Or try [`claude-tap`](https://liaohch3.com/claude-tap/), which I found only after vibing this tool to existence and then suddenly thinking about searching for something already in existence. Human after all!

<a name="appendix-1"></a>

### Appendix 1: What's In the Request?

I actually asked Codex to analyze the trace and tell me what was there and why - this is the answer I got.

Also, sorry for putting non-human text in `HUMAN.md`!

| Name | What was sent | Useful or necessary for this answer? |
|---|---|---|
| Tool definitions | 14 tool schemas across four namespaces, including an executor with embedded docs for web search, shell commands, and image generation. Also includes timing, subagent, and computer-use tools. | Web search could verify current details or resolve uncertainty. Stable, high-level definitions didn’t inherently require it. The other tools had no clear use. |
| Base Codex instructions | Writing style, formatting, progress updates, approval rules, coding conventions, and workflows. | Style guidance could affect phrasing. Your prompt already specified the length and tone. |
| Desktop app instructions | Rules for media, files, worktrees, automations, chat management, and app-specific formatting. | No clear use for a plain-text answer. |
| Skills, connectors, and plugins | A catalog of installed skills, deferred tool namespaces, and recommended uninstalled plugins. | No clear use. The catalog supplied no subject-matter information. |
| Permissions and collaboration | Filesystem and network permissions, approval policy, Default mode, agent roles, and a rule disabling proactive delegation. | Relevant to what Codex could do, unnecessary for the definitions. |
| Workspace instructions and environment | Your `@@@` protected-section rule, working directory, PowerShell shell, workspace roots, and permission profile. | Unnecessary. The prompt didn’t involve files or commands. |
| Client date and time zone | The client date and `Asia/Jerusalem`, with instructions to use them for user-facing dates and schedules. | Unnecessary for the question as asked. |
| Open and selected Page context | Two Page snapshots plus instructions for interpreting them. Both Page IDs were null, and there was no selected document view. | No Page content was available to use. |
| Model and verbosity | `model: gpt-6.1-sol` and `text.verbosity: low`. | The model field selects what runs. Low verbosity reinforces “be terse.” Neither supplies facts. |
| Reasoning settings | The top-level request specifies `xhigh` effort, a `detailed` summary, and `all_turns` context. An appended configuration update specifies `low` effort. | Could affect how the request was processed. The trace shows both effort values and doesn’t establish which took effect. |
| Tool-use settings | `tool_choice: auto` and `parallel_tool_calls: false`. | Control whether and how tools can be called. No calls or results appear in the captured input. |
| Request and response controls | `response.create`, streaming on, `store: false`, reasoning-summary delivery options, and requests for encrypted reasoning and output fields. | Handle request execution and response delivery. No relevance to the definitions. |
| Cache, client, and message metadata | A prompt-cache key, app and turn identifiers, timestamps, client flags, and per-message role and provenance fields. | Operational bookkeeping. Message roles distinguish your prompt from app instructions, but these fields add no subject facts. |
| Access program setting | `access_programs.cyber: standard`. | No relevance to the question. |
