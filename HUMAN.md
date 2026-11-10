# Why I Made This Project

`tl;dr` - why does a **21-tokens** question become a **~27k-tokens** request?

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

Also, sorry for putting non-human text in `HUMAN.md`! Here's what Codex had to say:

> For a Codex mode designed to answer short, standalone questions, I estimate **3,150–3,300 tokens for the serialized request**, about **87% smaller** than the 25,379-token estimate for this capture. That keeps all the existing metadata, permissions, client time, and request controls. It assumes Codex can skip loading the tool catalog and app context, and replace its general instructions with a 100–250-token version.

> The **question itself is 21 tokens**. The actual minimum for Codex is unknown. The trace shows which fields were sent, but it doesn’t establish which the client or server requires. I’ve counted those uncertain fields as **0 savings** in this estimate.

| Name | What was sent | Est. tokens (% of request) | Useful for this answer? | Est. tokens saved in a short-answer mode |
|---|---|---:|---|---:|
| Tool definitions | 14 tool schemas, including embedded documentation for web search, shell commands, and image generation. | 11,449 (45.11%) | Web search could verify uncertain facts. The other tools had no clear use. | **11,449** if routed without tools |
| Base Codex instructions | Writing style, formatting, approvals, and coding workflows. | 4,371 (17.22%) | Could shape the wording. Your question already specified the length and tone. | **4,121–4,271**, keeping 100–250 for basic instructions |
| Skills, connectors, and plugins | Installed skill catalog, deferred tool namespaces, and recommended plugins. | 3,103 (12.23%) | No skill or connector was needed. | **3,103** if the catalogs load only when needed |
| Desktop app instructions | Rules for files, media, worktrees, automations, chats, and app formatting. | 2,596 (10.23%) | No desktop workflow was involved. | **2,596** if omitted for plain-text answers |
| Cache, client, and message metadata | Cache key, IDs, timestamps, client flags, message roles, and provenance. | 1,958 (7.72%) | Message roles identify the question. The rest mainly supports request handling. | **0** assumed. Some fields may be required or handled outside the model context. |
| Permissions and collaboration | Filesystem and network permissions, approval policy, collaboration mode, and subagent rules. | 876 (3.45%) | Governs available actions. The question required no workspace access or delegation. | **0** assumed. Kept as runtime policy. |
| Open and selected Page context | Page snapshots and instructions for interpreting them. Both Page IDs were null. | 479 (1.89%) | No Page content was available to use. | **479** if the client can omit empty snapshots and their instructions |
| Workspace instructions and environment | Your `@@@` editing rule, working directory, shell, and workspace roots. | 332 (1.31%) | No files, commands, or workspace references were involved. | **332** if workspace context loads only when needed |
| Client date and time zone | Client date, `Asia/Jerusalem`, and scheduling guidance. | 76 (0.30%) | No date-sensitive answer was requested. | **0** assumed. Kept because its omission behavior is unknown. |
| Request and response controls | Request type, streaming, storage flag, summary delivery, and requested encrypted output fields. | 42 (0.17%) | Supports processing and response delivery. | **0** assumed |
| Reasoning settings | Top-level `xhigh` effort, summary and context settings, plus an appended `low` effort update. | 37 (0.15%) | Could affect generation. The trace doesn’t show which effort took effect. | **0** assumed |
| Your question | The request for one terse paragraph each on Aerospike and Akka. | 21 (0.08%) | Essential. It specifies the subjects and format. | **0** |
| Model and verbosity | `gpt-6.1-sol` and low text verbosity. | 17 (0.07%) | Selects the model and reinforces “be terse.” | **0** assumed |
| Tool-use settings | Automatic tool selection and parallel calls disabled. | 12 (0.05%) | Governs tool calls. The trace doesn’t show whether one was made. | **0** assumed |
| Access program setting | `access_programs.cyber: standard`. | 10 (0.04%) | No bearing on the definitions. | **0** assumed. Kept as a policy field. |
| **Total** | | **25,379 (100%)** | | **22,080–22,230** |

The biggest lever is **whether Codex loads tools before it knows it needs them**. The tool catalog alone accounts for just over half the estimated savings. These are payload estimates. The trace reports 27,064 input tokens, of which 20,736 were cached, so an 87% smaller request wouldn’t necessarily mean an 87% lower bill.



### Appendix 2: Is this already solved?

* Session viewer (works with Codex too, despite the name): https://liaohch3.com/claude-tap/
* Context minimizer plugin: https://github.com/mksglu/context-mode

I found out these two after this repo was already created; I'll dig deeper into them to know whether I should kill this project or let it be..
