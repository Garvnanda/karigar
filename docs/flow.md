# Code flow

## Entry points
- `run.py:main` — CLI. `order "<request>"` runs one request; `calibrate` records a cast weight; `packs` lists domain packs.
- `probe/server.py:main` (`python -m probe`) — Phase 6.5 Nonilion probe, a stdlib `ThreadingHTTPServer`. Routes (each also without `/v1`): `GET /` health (no key), `GET /v1/models`, `GET /v1/models/karigar-probe`, `POST /v1/chat/completions` (JSON or SSE stream), `GET /probe/log?n=` (key), `GET /probe/image.png` (no key, 1 px PNG for the Markdown image test). Every request is first written to `PROBE_LOG` (JSONL, secrets redacted, data: URIs as type+length, strings > 2000 chars cut, rotated to `.1` past 20 MB), then auth (`Authorization: Bearer PROBE_API_KEY`, else 401), then the route. Chat replies describe what was received; `probe delay N` / `probe stream N` in the last user message override `PROBE_DELAY_S` / `PROBE_STREAM_LINES`. After a chat reply a `done` event (elapsed_s) or, if the client hung up, a `disconnected` event is logged. Not connected to `karigar/`.
- No Karigar server yet. Phase 7 adds an OpenAI-compatible `/v1/chat/completions` endpoint and a Blender worker; agents imported into Nonilion ("Other") call it (docs/nonilion.md).

## Request / data flow (`order`)
1. `run.py` imports the packs (`karigar/packs/jewellery`, `karigar/packs/hardware`), which register themselves in `core/registry.py`.
2. `core/orchestrator.py:Orchestrator.handle` creates `out/ORD-<timestamp>/` and runs the five agents through the `Transport`:
   1. **Sakhi (brief)** → `packs/jewellery/brief.py:parse`. Tries the LLM (`core/llm.py:complete_json`), falls back to regex. Returns `(Brief, question)`; a question ends the order with `needs_info`.
   2. **Jauhari (plan)** → `pricing.py:plan`. Reads `data/rate_card.json`, loss % from `core/calibration.py` (the `CalibrationStore` passed as `Orchestrator(calibration=...)`, default `data/calibration.json`). Turns old gold / target weight / budget into a modelled-gram target using `core/gold.py`. An impossible request ends with `infeasible` + options.
   3. **Naqqash (design)** → `designer.py:propose`. LLM variants validated against `schema.py:DesignSpec`; invalid ones are replaced with deterministic fallbacks.
   4. **Karigar (build)** → `JewelleryPack.solve`. `dfm.py:scale_bounds` gives the castable scale range; `core/solver.py:solve_monotone` finds the scale where `geometry.py:gold_volume × density` hits the target.
   5. **Chitrakar (render)** → `JewelleryPack.deliver`: `geometry.build`, `render.export_stl`, `render.export_glb`, `render.render_views`, plus `job_card.json`.
   6. **Jauhari (quote)** → `pricing.py:quote` → `quote.json`.
3. `order.json` summarises the order. `ConsoleTransport` prints every message.

## Request / data flow (`calibrate`)
`CalibrationStore.record` appends `{designed_g, actual_g}` to `data/calibration.json`; loss % = mean of the last 20 records.

## Modules
| Module | Responsibility | Talks to |
|---|---|---|
| `core/orchestrator.py` | Shop-floor flow, five agents | registry, transport, calibration |
| `core/registry.py` | `DomainPack` interface, `Plan`, `Solved` | packs |
| `core/solver.py` | Monotone scale solver (log-log interpolation) | — |
| `core/gold.py` | Purity, density, exchange targets | — |
| `core/calibration.py` | Per-workshop learned loss | `data/calibration.json` |
| `core/llm.py` | Optional LLM JSON calls, `.env` loading, key redaction | `claude` CLI → AgentRouter, or Anthropic API |
| `core/transport.py` | Output channel (Console; Nonilion stub) | — |
| `packs/jewellery/schema.py` | `Brief`, `DesignSpec` (Pydantic) | — |
| `packs/jewellery/brief.py` | Sakhi: parse request | llm |
| `packs/jewellery/designer.py` | Naqqash: variants | llm, schema |
| `packs/jewellery/pricing.py` | Jauhari: plan + quote | gold, `data/rate_card.json` |
| `packs/jewellery/dfm.py` | Casting rules (spec-level today) | schema |
| `packs/jewellery/geometry.py` | bpy/bmesh builders, volume | bpy |
| `packs/jewellery/render.py` | Studio, Cycles, STL/GLB | bpy |
| `packs/hardware` | Roadmap placeholder | — |

## External services
- LLM (`core/llm.py:complete_json`), optional. Backend from `KARIGAR_LLM_BACKEND` (auto/agentrouter/anthropic/none), config from `.env`:
  - `agentrouter`: subprocess `claude -p … --tools "" --append-system-prompt` with `ANTHROPIC_BASE_URL=https://agentrouter.org`; prompt on stdin; timeout `KARIGAR_LLM_TIMEOUT_S`.
  - `anthropic`: Anthropic SDK.
  - Any failure → None → caller uses its deterministic path (`brief._regex_parse`, `designer.fallback`).
- Nonilion: no Bot API exists yet. `NonilionTransport` stays a stub; Nonilion reaches Karigar as an imported OpenAI-compatible service (Phases 6.5–8).
