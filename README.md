# Karigar: an AI artisan for anything that gets made

**Flagship pack: Jeweller's Shop.** Bring your old gold, and leave with a new design that carries exactly that gold, ready to cast.

Five agents work one order across the shop floor:

| Agent | Zone | Job |
|---|---|---|
| **Sakhi** | Counter | Understands the request (English or Hinglish) and asks a follow-up question when something essential is missing |
| **Jauhari** | Pricing desk | Turns old gold, a target weight or a budget into a target weight; refuses impossible requests with real options; writes the quote |
| **Naqqash** | Design studio | Proposes 3 design variants as validated specs (LLM, with a deterministic fallback) |
| **Karigar** | Workshop | Solves each design to the target weight, checks that it can be cast, exports the STL and job card |
| **Chitrakar** | Photo studio | Catalog renders in Cycles and a GLB for AR |

## Quick start

```bash
python3.13 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python run.py order "Nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai, size 2-6" --quality preview
./venv/bin/python run.py order "18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 12"
./venv/bin/python run.py order "purani 22K chain 6.2g se 22K ruby lotus pendant banao"
./venv/bin/python run.py order "18K 1 ct diamond ring under 10k, size 12"        # impossible request: explains, offers options
./venv/bin/python run.py order "kuch sundar sa bana do"             # unclear request: asks a follow-up
./venv/bin/python run.py calibrate --workshop dariba-01 --designed 18.58 --actual 17.95
```

- **Output:** each order writes to `out/ORD-…/v1..v3/`: `render_*.png`, `casting.stl` (mm, gold only), `model.glb` (real-world scale, for AR), `job_card.json`, `quote.json`. A full order summary goes to `order.json`.
- **Render quality:** `--quality draft|preview|final` (480/720/1400 px).
- **GPU:** set `KARIGAR_GPU=CUDA` (or `OPTIX`, `HIP`, `METAL`) to render on your laptop's GPU.
- **LLM:** set `ANTHROPIC_API_KEY` to use the LLM for the brief and the designer (model via `KARIGAR_MODEL`). Without a key, everything still runs on the deterministic fallbacks, so the demo never depends on the network.

## How the weight solving works

1. **Fine gold.** old weight × the stated karat's purity × (1 − melting loss) gives the fine gold, e.g. 18.4 g × 0.916 × 0.98 = 16.52 g.
2. **Finished weight.** fine gold ÷ new purity gives the finished weight of the new piece (18.03 g at 22K).
3. **Modelled weight.** finished weight ÷ (1 − workshop loss) gives the weight to model (18.59 g at 3%). The workshop loss is learned from `calibrate` records.
4. **Solve.** The solver scales the design's cross-section (ring size stays fixed) and measures the real mesh volume × alloy density. It converges in 4–5 passes to within ±0.3%.
5. **Castability.** Scaling is bounded by casting rules (minimum thickness and width, claw size, bail hole). If the target falls outside those bounds, Karigar says so and offers options instead of returning a bad design.

Claim **"within ±2% after finishing"** in the pitch, not the solver's ±0.3%. Real casting variance is larger, and calibration is what closes the gap.

## Layout

```
karigar/core/          shared engine, domain-agnostic
  gold.py              assay-aware gold arithmetic
  solver.py            monotone constraint solver (log-log interpolation)
  calibration.py       per-workshop learned loss (the data moat)
  orchestrator.py      the five-agent shop-floor flow
  transport.py         Console now; NonilionTransport stub for the Bot API
  registry.py          DomainPack interface
karigar/packs/jewellery/
  schema.py            Brief + DesignSpec (the only things the LLM may produce)
  brief.py             Sakhi: LLM + regex fallback, follow-up questions
  designer.py          Naqqash: LLM variants validated against the schema
  geometry.py          bpy/bmesh builders: ring + solitaire head, bangle, lotus/coin pendant
  dfm.py               casting rules (move to the shop knowledge base)
  pricing.py           Jauhari: plans, impossible-request handling, quotes
  render.py            studio, materials, Cycles, STL/GLB export
karigar/packs/hardware/  roadmap slot (CadQuery enclosures to PLA grams)
data/rate_card.json    SAMPLE rates: replace with the shop's own (Nonilion knowledge base)
```

## Nonilion probe (Phase 6.5)

A throwaway OpenAI-compatible endpoint (`probe/`, standard library only) that logs everything Nonilion's
**Import → Other** sends, so the real service (Phase 7) is built on facts. It does not touch `karigar/`.

| Env var | Default | Meaning |
|---|---|---|
| `PROBE_API_KEY` | required | Key Nonilion must send as `Authorization: Bearer …`; the server will not start without it |
| `PORT` | 8080 | Render sets it |
| `PROBE_LOG` | `probe/requests.jsonl` | JSONL request log (gitignored; ephemeral on Render) |
| `PROBE_DELAY_S` | 0 | Seconds before the reply (spread across the progress lines when streaming) |
| `PROBE_STREAM_LINES` | 3 | `progress i/N` lines sent before the reply when streaming |

1. **Deploy (Render, free):** New → Web Service → this repo. Runtime Python, build command `echo probe-has-no-deps` (do **not** install requirements.txt: it pulls bpy), start command `python -m probe`, instance type Free, health check path `/`. Env: `PROBE_API_KEY` = a long random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Free instances sleep after ~15 min idle; the first request then takes ~1 min, so open `https://<app>.onrender.com/` in a browser before testing. No-Render alternative: `python -m probe` locally + `cloudflared tunnel --url http://localhost:8080`.
2. **Check:** `curl -H "Authorization: Bearer $KEY" https://<app>.onrender.com/v1/models` → `karigar-probe`.
3. **Import in Nonilion:** room → agent panel → IMPORT → Other. API key = `PROBE_API_KEY`; Where is it? = `https://<app>.onrender.com/v1`; instructions = `You are the Karigar probe.`; press **Test the key**.
4. **Read the log:** `https://<app>.onrender.com/probe/log?n=50` with the same Bearer header (curl, or a browser header extension). Each request is an `event: request` entry (path, prefix and agent used, headers/query redacted, body, client IP = last X-Forwarded-For hop); chat replies add `done` (elapsed_s) or `disconnected` (Nonilion hung up — its timeout). Requests without the key are logged as a summary only (`body_bytes`, body not read).
5. **In the room chat:** say anything — the reply lists the agent, messages/roles, stream yes/no, ids seen, tools, headers, and ends with a Markdown table and an image (does it render?). Then: `probe delay 30`, `probe delay 120`, `probe delay 300` (non-stream or stream timeout), `probe stream 10 probe delay 60` (are progress lines shown live?), a second message (is history sent?), a photo upload (`image parts: 1`?). **Several agents:** import the probe twice with different base paths — `https://<app>.onrender.com/sakhi/v1` and `https://<app>.onrender.com/karigar/v1` — then `@`-mention one, then the other; each reply says `agent: sakhi` / `agent: karigar`, and the log's `agent` field shows which one Nonilion called (does a message to one agent also reach the other? is history shared?).

Limits (see docs/decisions.md): body ≤ 8 MB (413), JSON ≤ 100,000 nodes / depth 64 (400), 30 s to send a request (408), ≤ 8 delayed/streaming replies at once (429), ≤ 64 connections (503), log lines ≤ 64 KB, log rotated at 10 MB keeping 5 old files. Agent names in `/<agent>/v1` must match `[a-z0-9_-]{1,32}` (else 404).
6. Write each answer into docs/nonilion.md's "Unknowns" table.

## Status: real vs. still to do

**Working and tested:** every brief → plan → design → solve → render → export → quote path; impossible and unclear requests; calibration; all three piece types; watertight STL output.

**Next, in order:**
1. **Nonilion transport.** Map `say / progress / send_file / move_to` onto the Bot API once Nonilion shares the developer guide. Use one bot identity per agent.
2. **Read the rate card and casting rules from the room's knowledge base** instead of `data/`.
3. **AR viewer page** (`<model-viewer>` + GLB) hosted on Render, with a QR code in the chat.
4. **Turntable GIF** (rotate the camera and render 24 frames at draft quality).
5. **"@Karigar make it 2 g lighter"**: re-run `solve()` on the chosen spec with a new target. It takes seconds.
6. **Smarter budget mode:** cap the band at a natural weight and spend the rest on a bigger stone.
7. **Hardware pack:** a CadQuery builder for the same engine.

**Default values to confirm on the field visit:** melting loss (2%), casting loss (3%), making-charge percentages, casting minimums in `dfm.py`, and the ring and bangle size tables.
