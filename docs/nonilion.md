# Nonilion: what it supports for Karigar

Checked 2026-11-11 against every public page: /documentation (Welcome, Getting Started, Platform Overview, Key
Milestones, FAQ, Security), /changelogs, /discover/integrations, /solutions/*. The developer API is listed as
**"API Reference — Soon"**; no Bot API, webhook or SDK is documented. Everything marked "marketing" below comes
from product pages, not docs. Verify it in the app (QUESTIONS.md) before the demo depends on it.

## Capability map (spec's Nonilion table)
| What Karigar wants | Supported? | Evidence |
|---|---|---|
| "Your own code" route: webhook + Bot API | **No (not yet)** | Docs sidebar: "API Reference — Soon" |
| Agents in the room, deployed by us | **Yes, manually** | Changelog Jul 2026 "Office Room Settings Overhaul": deploy and manage agents (Claw, AI Agents) from the room |
| Agent calls our code (tools) | **Likely** | Integrations page: OpenClaw skills incl. `api-gateway` ("calling third-party APIs"), `n8n-workflow-automation`, "MCP runtime for live multimodal and agentic workflows". Custom MCP/HTTP tool not confirmed |
| Bring our own Claude key | **Yes** | Solutions pages: BYOK, "choose the model per task" |
| Room knowledge base (gold rate doc) | **Yes** | "Agents retrieve from your connected knowledge base using hybrid search"; staff "point at the right knowledge sources" |
| Several agents with roles (Sakhi, Jauhari, …) | **Yes** | "Multiple agents can hold different roles on the same goal and share the room's context and knowledge base" |
| Approval gate before an action | **Yes (marketing)** | "Any action you mark as consequential stops for explicit human approval" |
| Audit log of tool calls | **Yes (marketing)** | "Every tool call, decision, and error is recorded" |
| Formatted chat replies | Unverified | Room settings have a "messages" section; agent chat format not documented |
| Files out (STL, job card, renders) | Unverified | Room settings have a "files" section; whether an agent can post a file is not documented. Fallback: links to files we host |
| Files in (reference photo) | Unverified | Same "files" section; agent read access not documented |
| Voice summary | Unclear | Solutions page markets voice agents; changelog lists "Voice Based AI Agent NPC" as **Planned** |
| @mention an agent in chat | Not documented | — |
| Walk-to / office actions by an agent | Not documented | Agents have "room presence"; movement actions not described |
| Progress posts during long jobs | Not documented | — |

## In-app findings
- 2026-11-11 (screenshot from the user): the room's agent panel has tabs ROOM · HIRE · IMPORT · MARKET. IMPORT →
  "Pick a platform": Grok, ChatGPT ("your agent or GPT"), Claude ("your agent from Claude"), Gemini, Mistral, Coze,
  Meta, Other ("any other AI service"). An imported agent is built and hosted on its own platform, so its tools
  (GPT Actions, Claude MCP connectors, or our own endpoint under Other) come from there.
- 2026-11-11 (screenshot): IMPORT → **Other** ("Connect to Other · any other AI service") asks for: **API key**
  ("any key your service gave you"; or one saved in Settings → AI Providers), **Where is it?** = a base URL
  `https://…/v1` (example: Groq `https://api.groq.com/openai/v1`), **Its instructions** (system prompt),
  avatar, and a **Test the key** button. This is an OpenAI-compatible chat endpoint: Nonilion will call
  `{base}/chat/completions` (and probably `{base}/models` for the key test). **Karigar can be that service.**

- 2026-11-11 (pasted list): **HIRE** offers 6 prebuilt staff (Atlas "Head of Office", Social Media Lite Agent,
  Convertor, Blog Editorial Agent, Mr. Noni "Local Console", Iris "Customer Support Lead") and ~50 "Grok bots"
  (free, run on your own key: Bot Builder, Code Pair, Customer Support, Bookkeeper, Translator, …). All are fixed
  personas with no way shown to attach our code, so HIRE is not our route. Atlas/Iris could share the room as
  background staff for the demo.

### Unknowns about the "Other" route (answer with the probe endpoint, Phase 7)
| Question | Why it matters |
|---|---|
| Which paths does "Test the key" call (`/models`? a tiny chat call?) | Must answer it or the import fails |
| Does each call carry the full chat history, and any room / user / conversation ID? | Order state per conversation |
| `stream: true`? How long does Nonilion wait for a reply? | Pipeline takes minutes; streaming could carry progress lines |
| Does it render Markdown, tables, `![](url)` images, links in replies? | Renders and files shown as images or links |
| Are uploaded photos sent as `image_url` parts? | Photo-to-spec (P1) |
| Does it send `tools` / expect tool calls? | We ignore them, but must not error |
| Can 2+ imported agents point at different base URLs on our server? | One character per agent (Sakhi, Jauhari, …) |

## What this means
The Bot API doesn't exist yet, but the **Import → Other** route does the same job: Karigar runs an
OpenAI-compatible `/v1/chat/completions` endpoint on Render, and an agent imported into the room points at it.
Nonilion sends the chat; Karigar's own code (brief → plan → design → solve → render → quote) writes the reply.
No third-party agent sits in between, so no LLM outside Karigar can change a number.
Decisions: decisions.md "Nonilion route: Karigar is an OpenAI-compatible service". Plan: implementation.md Phases 7–8.
