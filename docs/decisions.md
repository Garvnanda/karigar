# Decisions
Append-only. Newest at bottom. Entries dated 2026-11-11 marked "existing" record choices already in the code before the docs existed.

## 2026-11-11 — The LLM writes specs, code writes numbers (existing)
- **Context**: Whole pipeline.
- **Decision**: The LLM only produces `Brief` / `DesignSpec` JSON validated by Pydantic. Geometry, weights, rules and prices come from deterministic code and data.
- **Why**: Spec "Why it is more than a chatbot"; prices and weights must be traceable.
- **Alternatives**: LLM-generated geometry or prices. Rejected: not checkable.

## 2026-11-11 — Every LLM call has a deterministic fallback (existing)
- **Context**: `core/llm.py`, `brief.py`, `designer.py`.
- **Decision**: No API key or any LLM failure → regex brief parser and fixed design variants.
- **Why**: The demo must never depend on the network.
- **Alternatives**: Hard dependency on the LLM. Rejected for demo risk.

## 2026-11-11 — One monotone scale knob per design (existing)
- **Context**: `core/solver.py`.
- **Decision**: The solver scales the cross-section (ring size fixed) and interpolates in log-log space between castable bounds.
- **Why**: Volume grows monotonically with scale; converges in 4–5 builds. Spec allows bisection for one monotone parameter.
- **Alternatives**: Multi-parameter bounded search (scipy). Deferred until a family needs it (budget mode, Phase 3).

## 2026-11-11 — Blender as a Python module, run inside WSL (existing)
- **Context**: `requirements.txt`, `venv/`.
- **Decision**: `bpy` 5.0.1 in a WSL Python 3.11 venv. Tests and the CLI run through `wsl`.
- **Why**: bpy wheels and the existing venv are Linux; the Render worker will be Linux too.
- **Alternatives**: Windows venv. Not set up; would diverge from the deployed worker.

## 2026-11-11 — P0 phase order: engine first, service and Nonilion last
- **Context**: docs/implementation.md.
- **Decision**: Phases run baseline/tests → scope/contracts → ring families → weight/solver → mesh checks → quote/rate → edits → service → Nonilion → user sim → demo.
- **Why**: Nonilion work is blocked on its developer guide; the engine gaps (mesh checks, motif ring, edits) are needed by the demo regardless and can be built now.
- **Alternatives**: Nonilion first. Rejected: blocked, and a connected bot with a weak engine still fails the demo.

## 2026-11-11 — Runtime data stays out of git
- **Context**: `.gitignore`.
- **Decision**: Ignore `venv/`, `out/`, `data/calibration.json`, `data/orders.db`.
- **Why**: Machine-specific or generated. `data/rate_card.json` stays tracked as sample config.
- **Alternatives**: Commit calibration records. Rejected: they are per-workshop data, not code.

## 2026-11-11 — Blender MCP: dev tool now, constrained drawer agent later
- **Context**: User wants a Blender MCP so work happens in Blender, and later a group of agents that decide a design plus one agent whose only job is to draw in Blender.
- **Decision**: Two stages. (1) Now: a Blender MCP server connected to Claude Code as a dev tool to watch builds, inspect meshes and debug renders. The product pipeline stays headless `bpy`. (2) Later: a drawer agent that may only call Karigar's own parametric builder ops (exposed as MCP tools, e.g. add band / head / motif with typed parameters), never arbitrary Blender Python. Every call is logged into the spec as an op list, so replaying the ops rebuilds the same mesh. Volume, weight, rule checks and pricing stay in code.
- **Why**: Keeps the spec's "LLM never draws a number" guarantee and determinism (same spec → same mesh) while giving the agent a real drawing role. Arbitrary code execution through MCP would be unreproducible and a security hole.
- **Alternatives**: Agent sends raw `bpy` code through MCP. Rejected: not deterministic, not checkable, injection risk. No MCP at all. Rejected: user wants it.

## 2026-11-11 — Nonilion route: manual Nonilion agents call Karigar as a tool
- **Context**: Phases 7–8. Public Nonilion docs list the API as "Soon"; no Bot API or webhook exists (docs/nonilion.md). User will create agents in Nonilion by hand.
- **Decision**: Invert the spec's design. Karigar becomes a service on Render exposing tools (MCP server over HTTP, plus plain HTTP endpoints as a fallback for an `api-gateway` skill): start order, order status, edit order, get quote. Results carry URLs to files we host (renders, STL, job card). Agents are set up by hand in the room (Sakhi at the counter, Jauhari for pricing, …), each with a persona prompt, our Claude key (BYOK), the room KB and the Karigar tools. The agent must relay numbers from tool results only; tool replies carry a ready-to-post summary so the agent never does arithmetic.
- **Why**: It's the only route available now, and it matches "if required I will start agents in Nonilion manually". The engine and its deterministic guarantees stay unchanged. Later, when the Bot API ships, `NonilionTransport` can be added beside it.
- **Alternatives**: Wait for the Bot API. Rejected: no date, demo can't depend on it. Browser automation of the Nonilion UI. Rejected: brittle, against the platform's intent.
- **Open**: whether a Nonilion agent can attach a custom MCP server or HTTP API, post files and images, and read uploads (QUESTIONS.md). The plan holds either way: links instead of attachments if needed.
- **Superseded** the same day by the next entry.

## 2026-11-11 — Nonilion route: Karigar is an OpenAI-compatible service (supersedes the entry above)
- **Context**: In-app check (docs/nonilion.md): Import → Other takes an API key, a base URL `https://…/v1` and a system prompt, i.e. any OpenAI-compatible chat endpoint.
- **Decision**: Karigar serves `/v1/chat/completions` (and `/v1/models`) itself. Each imported Nonilion agent points at Karigar; the incoming messages go through Karigar's own brief agent and pipeline, and the reply text is written by code (numbers) plus Karigar's own LLM (wording only). Several agents (Sakhi, Jauhari, …) can point at different paths if Nonilion allows it. MCP is not used for Nonilion; it stays for the Blender drawer agent.
- **Why**: Available today, needs no Nonilion API, and keeps every number inside Karigar's code. A Claude/ChatGPT agent calling our tools would add an LLM that could restate numbers wrongly.
- **Alternatives**: Imported Claude/ChatGPT agent calling a Karigar MCP/Actions API. Kept as a fallback if the "Other" route can't handle long jobs. Waiting for the Bot API. Rejected.
- **Open**: timeouts, streaming, history and conversation IDs, Markdown/image rendering (docs/nonilion.md table). Answered by a probe endpoint before building the real service.

## 2026-11-11 — Karigar is a standalone service; Nonilion is one adapter
- **Context**: User: "make the full service workable on our own, easy to migrate to any service in the future", then point the Nonilion agent at it.
- **Decision**: One transport-free core (`KarigarService`: start order, continue conversation, edit, status, quote) with thin adapters: CLI (`run.py`), a plain JSON HTTP API, and the OpenAI-compatible `/v1/chat/completions` that Nonilion imports. Moving to another platform = a new adapter, no engine change. The Nonilion agent's "instructions" field holds a short persona; the real behaviour lives in Karigar.
- **Why**: Nonilion's API isn't out; platform choice may change; the engine must be testable without any platform.
- **Alternatives**: Build directly against Nonilion's chat shape. Rejected: lock-in and untestable offline.

## 2026-11-11 — LLM provider: AgentRouter through the Claude Code CLI
- **Context**: User picked AgentRouter as the API provider. Lessons carried over from hackerrank-orchestrate-october26 (its docs/decisions.md, 2026-10-25), measured there:
  - Direct HTTP to AgentRouter → `401 unauthorized client detected`; only approved coding clients work. Running the official `claude -p` headless is supported. Spoofing client headers was rejected (bypasses provider access control, ban risk).
  - Native function tools fail intermittently (≈ 25% success) → `--tools ""` and our own JSON output instead.
  - Replacing the system prompt → `400 content-blocked`; `--append-system-prompt` works. Very short meaningless prompts were also `content-blocked`.
  - Models then: Claude models and deepseek-v4-flash → 503; gpt-6-astra / gpt-5.6-sol → 400; **gpt-6.1-sol** worked. $1 / $5 per 1M tokens in/out.
  - Latency 9 s typical, but **up to 20 min** per call observed.
  - CLI is single-shot: history is flattened into one prompt; prompt goes over stdin (key never in argv).
- **Decision**: `karigar/core/llm.py` backend `agentrouter` runs `claude -p --bare --disable-slash-commands --strict-mcp-config --tools "" --model $KARIGAR_MODEL --output-format json --max-turns 1 --append-system-prompt <system>` with `ANTHROPIC_BASE_URL=https://agentrouter.org`, `ANTHROPIC_AUTH_TOKEN=$AGENTROUTER_API_KEY`, `ANTHROPIC_API_KEY=""`, `MAX_THINKING_TOKENS=0`. Hard timeout `KARIGAR_LLM_TIMEOUT_S` (45 s); any failure returns None and the deterministic path answers. Key redacted from every log line. An `anthropic` SDK backend stays for migration. Config in git-ignored `.env` (`.env.example` lists keys).
- **Why**: The LLM only shapes briefs and design variants; with 20-minute worst-case latency it must never block a reply, and the demo must run offline.
- **Consequences**: LLM calls run in the worker, never in a chat request handler (Phase 7). The Render worker image needs Node + the `claude` CLI next to bpy. Vision (photo-to-spec, critic) through this CLI is unproven: P1, test before relying on it.
- **Measured here 2026-11-11**: live call from WSL (claude CLI 2.1.276), `gpt-6.1-sol`, Hinglish brief → valid JSON in 13.6 s. Key copied from hackerrank-orchestrate-october26's `.env` at the user's request.
- **No Anthropic key needed** (user has none): the `claude` CLI is only the approved client program; it authenticates to AgentRouter with the AgentRouter key (passed in the CLI's `ANTHROPIC_AUTH_TOKEN` variable) and AgentRouter serves the model. The `anthropic` backend is an unused option for a future provider move; `auto` never picks it without an `ANTHROPIC_API_KEY`.
- **Alternatives (provider)**: OpenAI-compatible HTTP to AgentRouter (blocked, 401). Anthropic API directly (kept as backend; needs a separate key). Local Ollama fallback (used last time; CPU-only and slow, not needed because the deterministic fallback exists here).

## 2026-11-11 — Shop numbers: sourced defaults, labelled "assumed", all in config
- **Context**: Phases 3–5. User: "search credible sources, tell me where you picked the numbers". Pages opened 2026-11-11. Every value moves into a config file (`data/`), and the quote/job card labels it "assumed — confirm with your caster/CA" until a shop overrides it.
- **Decision**:
  | Number | Value | Source |
  |---|---|---|
  | Density 24K / 22K / 18K / 14K yellow (g/cm³) | 19.32 / 17.75 / 15.45 / 13.05 | Sobling jewellery metal-weight table (https://sobling.jewelry/jewelry-metal-weight-conversion); 22K casting-alloy range 17.45–18.24 per Flume datasheet (https://www.flume.de/media/4b/38/62/1671071625/pimFile_0000006262.pdf). Alloy recipe shifts these; calibration absorbs it |
  | Min ring shank thickness | 1.5 mm (women's), 2.0 mm (men's) in high-karat gold | Ganoksin, "Tips for Avoiding Meltdown" (https://www.ganoksin.com/article/tips-avoiding-meltdown/) |
  | Min wall thickness (other parts) | 0.8 mm structural; 1.0 mm preferred | Stuller CAD/CAM production standards (0.8 mm structural, 0.45 mm bezel) (https://cdn.hackaday.io/files/1657037089437152/CADCAMProductionStandards.pdf); Ganoksin (≥ 1 mm) |
  | Min prong diameter | 0.8 mm (melee pinpoint can go to 0.45 mm) | Materialise gold design guide (https://i.materialise.com/materials/gold); Stuller (0.45 mm melee) |
  | Min opening / hole | 0.4 mm opening; 1.5 mm holes/slots | Stuller; Materialise |
  | Casting shrinkage (STL scale-up) | 1.0% | US patent 4283831: ~1% total across investment, burnout, casting, cooling (https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/4283831). Forum figures of 6–8% are anecdotal (Ganoksin) |
  | Casting + finishing metal loss | 3% default, learned per workshop by `calibrate` | Industry wastage quoted at 2–8% (BlueStone, https://blog.bluestone.com/what-is-wastage-in-gold-jewellery-and-are-you-being-charged-fairly/); no authoritative standard exists, which is why calibration matters |
  | Old-gold deduction (melting loss) | 2% (user choice); 0% if the old piece carries a BIS hallmark is a shop option | Business Standard: ~4% melting + wastage, none on hallmarked (https://www.business-standard.com/article/pf/selling-jewellery-can-be-difficult-112091800032_1.html); brands 2–5% (Kalyan 2–3%, Tanishq ~5%) per Digirake guide |
  | Hallmarking (BIS HUID) | ₹75 per piece | BIS (Hallmarking) Amendment Regulations 2026, effective 14 Sep 2026, up from ₹45 (SCC Online, https://www.scconline.com/blog/post/2026/09/18/bis-revises-hallmarking-fees-for-gold-and-silver-articles/) |
  | GST | 3% on gold + stones; **5% on making charges** (custom-made piece) | PKC India GST guide (May 2026): ready-made off the shelf = composite supply, 3% on everything; **custom-made = making charges taxed 5% as a service** (https://www.pkcindia.com/blog/gst-on-gold-2026-rate-on-jewellery-making-charges-coins-digital-gold-explained/); 3% on gold confirmed after GST 2.0 by Busy (https://busy.in/gst-rates/gold/). Karigar makes custom pieces, so 3% + 5%. Flag: confirm with a CA |
  | Making charge | 3.5% of gold value (user: "realistically 3–4%") | User choice, per-piece-type in config |
  | Ring sizes | Published Indian chart, sizes 1–30 → inner diameter, stored in `data/ring_sizes.json` | Charts disagree by ~0.1–0.3 mm between brands (Jewelove, Malabar, Tanishq). Use one brand's chart whole (Tanishq, https://staticimg.tanishq.co.in/pdf/find-your-ring-size.pdf, or Malabar) and cite it; shops can replace the file |
- **Why**: User asked for credible, cited numbers; none of these has a single legal standard except hallmarking and GST.
- **Changes from current code**: densities 17.8/15.5/13.1 → 17.75/15.45/13.05; ring min thickness 1.2 → 1.5 mm; existing `melt_loss_pct` and the new deduction merge into one 2% deduction (no double counting); hallmark fee and split GST added to the quote.

## 2026-11-11 — Hosting and rendering within a $50 budget
- **Context**: User: worker on the laptop (Intel integrated graphics, no usable GPU); "use Render for GPUs… can we show judges within $50?"
- **Finding**: Render has **no GPU instances**; its compute plans are CPU only (render.com/pricing: Free 512 MB; $7 for 0.5 CPU/512 MB; $25 for 1 CPU/2 GB; …). GPU rental elsewhere: RTX 4090 about $0.14–0.74/h (Vast.ai, RunPod) per 2026 comparisons (https://www.spheron.network/blog/runpod-vs-vastai-2026/, https://neurohive.io/en/guides/cloud-gpu-pricing/).
- **Decision**: Render hosts the thin service (OpenAI-compatible API, queue, output files): $0–7/month. The laptop worker (WSL, bpy, `claude` CLI) polls Render over HTTPS, so there is no tunnel. Renders use Cycles on CPU at draft/preview size; Phase 0 measures the time. If a preview takes over the spec's 20 s, rent one RTX 4090 for demo day (~$0.35/h × ~10 h ≈ $4) running the same worker image.
- **Budget**: Render ≤ $7 + optional GPU ≈ $5–10 + AgentRouter usage (13.6 s, < 1k tokens per call at $1/$5 per 1M) ≈ cents. Comfortably under $50.
- **Alternatives**: Blender on Render CPU (needs ≥ 2 GB, $25+/month, slower than the laptop). All on laptop + tunnel (Render barely used; the submission needs Render).

## 2026-11-11 — Product choices from the user (Q&A round)
- Bangles stay in scope (with rings and pendants).
- Replies mirror the jeweller's language (Hinglish in → Hinglish out); numbers and job cards in English.
- Gold rate: jeweller can set it in chat ("aaj ka rate 22K 14730"), stored with a timestamp; else the config rate if < 24 h old; else ask. Never estimated.
- Nonilion: import two agents, **Sakhi** (counter: brief, questions, quote) and **Karigar** (workshop: designs, solving, files).
- Blender MCP: user installs Blender 5.x desktop on Windows; the MCP server is scanned with skill-inspector before install.
- Weight proof (Phase 9): no real gold pieces. Prove the maths instead: mesh volume vs exact formula volumes for simple shapes (a plain band is an annulus: V = π·w·(R²−r²)), error < 0.5%; then show the calibration loop learning a workshop's real loss. Real pieces stay optional.

## 2026-11-11 — Budget is $50 of Render credits only; no cash spend
- **Context**: User: "I only have $50 Render credits, I don't have $50 to spend; short on time."
- **Decision**: No GPU rental and no other paid service. Renders run on the laptop CPU (Cycles, draft/preview sizes, low samples + denoise). Render usage must fit inside the $50 credits (thin service on the cheapest plan that stays awake during the demo). AgentRouter uses the existing key. Supersedes the optional GPU rental in "Hosting and rendering within a $50 budget".
- **Why**: User constraint.
- **Alternatives**: Rented GPU for demo day (rejected: needs cash).

## 2026-11-11 — Blender MCP server: official Blender Lab server, skill-inspector verdict CAUTION
- **Context**: Phase 0.5. Candidates: the official Blender Lab server (projects.blender.org/lab/blender_mcp, maintainer Blender Lab) and the community `ahujasid/blender-mcp`, renamed `mcp-for-blender` in Sep 2026, single maintainer.
- **Scan** (SkillSpector v2.12.0, `--no-llm`, commit `dbbf836ad4b1025f14a2b3b504c43903f39e0b04`, 2026-09-29):
  - `mcp/`: score 21/100, CAUTION. One HIGH `YR1` = README text `pip install git+https://…` (an install instruction, nothing executes it). Static coverage partial: 4,621 of 4,676 files are bundled Blender API/manual docs (`blmcp/data`, .rst + example .py), reviewed by sampling.
  - `addon/`: score 30/100, CAUTION. HIGH `AST1` = `exec(code, namespace)` in `mcp_to_blender_server.py:252` — the server's stated purpose ("running arbitrary Python code within Blender"), wrapped in a weak sandbox. LOW `AST7` getattr in the sandbox.
  - Manual review: binds `localhost:9876` only; no authentication on that socket (any local process can run code in Blender while the bridge is on); no outbound network calls, no secret/env reads beyond its own host/port/Blender path; `subprocess` only launches `blender --background`. Dependencies: `mcp[cli]>=1.2,<2`, `docutils`, `pyyaml`.
- **Decision**: Use the official server, verdict CAUTION, pending the user's approval. Guardrails: install the add-on from the Blender Lab extensions repo; install the MCP server pinned to commit `dbbf836` in its own environment; register it in this project's `.mcp.json` only; start the bridge only during dev sessions and stop it after; never expose port 9876 beyond localhost.
- **Alternatives**: `mcp-for-blender` (community, single maintainer; same arbitrary-exec design). No MCP (user wants it).
- **User answer (2026-11-11)**: approved the install and declined the usage guardrails ("I don't think we need guardrails, just install"). Installed Blender 5.3.0 desktop via winget (`C:\Program Files\Blender Foundation\Blender 5.3`); MCP server via `uv tool install` pinned to `dbbf836`. The pin and project-only `.mcp.json` stay (no cost); the bridge on/off rule is dropped. Note: desktop is 5.3.0 while the worker's bpy wheel is 5.0.1 — geometry code targets 5.0.1; the MCP is for viewing/debugging only.

## 2026-11-11 — Laptop CPU render timing (Phase 0 measurement)
- **Context**: Phase 0. Intel Core Ultra 7 155H, 22 threads in WSL, Cycles CPU, LLM off, 3 variants per order.
- **Measured**: draft (480 px, 16 samples, 1 view) 2.7–3.9 s render per variant; whole order 15–25 s (kangan 24.7, solitaire 17.2, pendant 14.6). Preview (720 px, 48 samples, 2 views) 22–74 s per variant; whole order 78–211 s. Solve 0–4 s per variant. Infeasible / needs_info orders ≈ 2–3 s.
- **Decision**: Chat replies use draft renders (fast enough on the laptop CPU); preview/final only on request in the background. No GPU needed (and none affordable — "Budget is $50 of Render credits only").
- **Also (Phase 0)**: `Orchestrator(calibration=...)` optional injection so tests never touch `data/calibration.json`; gem dispersion only set when the Principled BSDF exposes the socket (bpy 5.0.1 has none — fixed a crash that kept the solitaire order from finishing); golden weights in `tests/golden/gold_volume.json`, regenerated with `KARIGAR_REGEN_GOLDEN=1`.

## 2026-11-11 — Nonilion probe: stdlib server, log first, safe by default (Phase 6.5)
- **Decision**: `probe/` is a standard-library `ThreadingHTTPServer` (no new dependency), started with `python -m probe` on a Render free web service. Every request (including failed auth and 404s) is logged before routing, so "Test the key" is visible even if it calls an unexpected path. Header names containing authorization/key/token/cookie/secret/password are redacted (body keys too, except `*tokens` like `max_tokens`); the API key value is replaced anywhere in logged strings; data: URIs are logged as `{data_uri: mime, length}`; strings > 2000 chars are cut; the log rotates to `.1` past 20 MB; bodies > 25 MB get 413. `GET /` (health) and `GET /probe/image.png` need no key; everything else does. Delay/stream directives are capped at 900 s / 200 lines. Chat replies include a Markdown table and an image link to `/probe/image.png` to test rendering; a `disconnected` event with elapsed time measures Nonilion's timeout.
- **Why**: Phase 6.5 needs answers, not a framework; logging before auth catches whatever Nonilion sends; caps keep a public endpoint from filling the free-plan disk or holding threads forever.
- **Alternatives**: FastAPI/uvicorn (new dependency, not needed for a probe); request-bin services (third party sees the key and chat).

## 2026-11-11 — Ring size chart source: PNG Jewellers (Phase 1)
- **Context**: Phase 1. The charts named in "Shop numbers" failed: Tanishq PDF is image-only (no text layer, 10.9 MB), Malabar's page is a redirect loop, Jewelove has only sizes 10–18 in steps of 2. ORRA covers 7–26 only.
- **Decision**: PNG Jewellers' Indian ring size chart (https://www.pngjewellers.com/ring-bangle-size-guide, retrieved 2026-11-11), sizes 1–30 with circumference and inner diameter, used whole and cited in `data/ring_sizes.json`. Inner diameter is canonical. Its size-29 circumference (68.1 mm) is inconsistent with its diameter (22.0 mm ≈ 69.1 mm circumference); kept as published, flagged in the JSON.
- **Why**: Only complete, machine-readable 1–30 brand chart found; satisfies "one brand's chart, used whole, cited".
- **Alternatives**: Tanishq/Malabar via manual transcription by the user (slower); stitching brands (breaks "one chart").
