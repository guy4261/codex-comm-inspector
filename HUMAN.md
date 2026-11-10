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

I actually asked Codex to analyze the trace and tell me what was there and why - this is the answer I got. Numbers are estimations.

Also, sorry for putting non-human text in `HUMAN.md`!

| Name | What was sent | Useful or necessary for this answer? | Est. tokens (% of request) |
|---|---|---|---:|
| Tool definitions | 14 tool schemas, including embedded documentation for web search, shell commands, and image generation. | Web search could verify uncertain or current facts. The other tools had no clear use. | 11,449 (45.11%) |
| Base Codex instructions | Writing style, formatting, approvals, and coding workflows. | Could shape the wording. Your question already specified the length and tone. | 4,371 (17.22%) |
| Skills, connectors, and plugins | Installed skill catalog, deferred tool namespaces, and recommended plugins. | No clear use for two short definitions. | 3,103 (12.23%) |
| Desktop app instructions | Rules for files, media, worktrees, automations, chats, and app formatting. | No clear use for a plain-text answer. | 2,596 (10.23%) |
| Cache, client, and message metadata | Cache key, IDs, timestamps, client flags, message roles, and provenance. | Roles identify your question. The remaining fields mainly support request handling. | 1,958 (7.72%) |
| Permissions and collaboration | Filesystem and network permissions, approval policy, collaboration mode, and subagent rules. | Governs available actions. The definitions didn’t require workspace access or delegation. | 876 (3.45%) |
| Open and selected Page context | Page snapshots and instructions for interpreting them. Both Page IDs were null. | No Page content to use. | 479 (1.89%) |
| Workspace instructions and environment | Your `@@@` editing rule, working directory, shell, and workspace roots. | Unnecessary for a question that didn’t involve files or commands. | 332 (1.31%) |
| Client date and time zone | Client date, `Asia/Jerusalem`, and scheduling guidance. | Unnecessary for the question as asked. | 76 (0.30%) |
| Request and response controls | Request type, streaming, storage flag, summary delivery, and requested encrypted output fields. | Relevant to processing and delivery. | 42 (0.17%) |
| Reasoning settings | Top-level `xhigh` effort, summary and context settings, plus an appended `low` effort update. | Could affect generation. The trace doesn’t establish which effort took effect. | 37 (0.15%) |
| **Your question** | The request for one terse paragraph each on Aerospike and Akka. | Essential. It specifies the subjects and the format. | **21 (0.08%)** |
| Model and verbosity | `gpt-6.1-sol` and low text verbosity. | Selects the model and reinforces “be terse.” | 17 (0.07%) |
| Tool-use settings | Automatic tool selection and parallel calls disabled. | Relevant if a tool was called. The snapshot doesn’t show whether one was. | 12 (0.05%) |
| Access program setting | `access_programs.cyber: standard`. | No relevance to the definitions. | 10 (0.04%) |
