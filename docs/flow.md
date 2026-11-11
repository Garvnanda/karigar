# Code flow

## Entry points
- `run.py:main` — CLI. `order "<request>"` runs one request; `calibrate` records a cast weight; `packs` lists domain packs.
- `probe/server.py:main` (`python -m probe`) — Phase 6.5 Nonilion probe, a stdlib `ThreadingHTTPServer`. Routes (each also without `/v1`, or under `/<agent>/v1` with agent `[a-z0-9_-]{1,32}`, else 404): `GET /` health (no key), `GET /v1/models`, `GET /v1/models/karigar-probe`, `POST /v1/chat/completions` (JSON or SSE stream), `GET /probe/log?n=` (key), `GET /probe/image.png` (no key, 1 px PNG for the Markdown image test). Per request (`Handler._route`): split path into prefix/agent/route → auth check (`Authorization: Bearer PROBE_API_KEY`) → body: unauthenticated = never parsed (≤ 64 KB drained, else connection closed; only `body_bytes` logged); authenticated = > 8 MB 413, `_parse_json` pre-scan (≤ 100k nodes, depth ≤ 64) then `json.loads`, then `scrub()` → one `request` entry written to `PROBE_LOG` (ASCII JSONL, secrets redacted in path/query/headers/keys/values, data: URIs as type+length, strings > 2000 chars cut, lines ≤ 64 KB, rotated at 10 MB keeping `.1`–`.5`) → route (401 if no key). Any exception in a handler → one-line `error`/`timeout`/`disconnected` log event + OpenAI-style 500/408 JSON (`Handler._fail`). `ProbeServer` caps connections (64 → 503); sockets time out after 30 s; delayed/streaming chat replies are capped at 8 at once (429). Chat replies describe what was received; `probe delay N` / `probe stream N` in the last user message override `PROBE_DELAY_S` / `PROBE_STREAM_LINES`. After a chat reply a `done` event (elapsed_s) or, if the client hung up, a `disconnected` event is logged. Not connected to `karigar/`.
- No Karigar server yet. Phase 7 adds an OpenAI-compatible `/v1/chat/completions` endpoint and a Blender worker; agents imported into Nonilion ("Other") call it (docs/nonilion.md).

## Request / data flow (`order`)
1. `run.py` imports the packs (`karigar/packs/jewellery`, `karigar/packs/hardware`), which register themselves in `core/registry.py`.
2. `core/orchestrator.py:Orchestrator.handle` returns `core/result.py:JobResult(...).model_dump()` and runs the five agents through the `Transport`:
   1. **Sakhi (intake)** → `pack.intake(text)` (`core/registry.py:Intake`). Jewellery (`packs/jewellery/__init__.py:JewelleryPack.intake`):
      - gold-rate message ("aaj ka rate 22K 14730", no piece word) → `rates.py:parse_rate_message` → `GoldRateStore.set` (`data/gold_rates.json`, ISO timestamp) → `rate_set` reply. No order folder.
      - else `brief.py:analyse`: `core/lang.py:detect` (en / hinglish) → out-of-scope piece → `out_of_scope` + nearest piece; else draft = LLM JSON validated against `BriefDraft` (one repair call with the validation error) or `_regex_parse` → blocking fields missing → `needs_info` with up to 3 questions in one reply; else a `Brief` (`ring_size` → inner diameter via `sizes.py` + `data/ring_sizes.json`). Every reply string comes from `messages.py` in the request's language.
      Non-brief intakes end the order there. Otherwise `out/ORD-<timestamp>/` is created and Sakhi states the brief summary.
   2. **Jauhari (plan)** → `pricing.py:plan`. Reads `data/rate_card.json`, loss % from `core/calibration.py` (the `CalibrationStore` passed as `Orchestrator(calibration=...)`, default `data/calibration.json`). Turns old gold / target weight / budget into a modelled-gram target using `core/gold.py`. An impossible request ends with `infeasible`: `explanation` plus `infeasible {binding_constraint, best_achievable, alternatives ≥ 2}` from `Plan`.
   3. **Naqqash (design)** → `designer.py:propose`. LLM variants validated against `schema.py:DesignSpec`; invalid ones are replaced with deterministic fallbacks.
   4. **Karigar (build)** → `JewelleryPack.solve`. `dfm.py:scale_bounds` gives the castable scale range; `core/solver.py:solve_monotone` finds the scale where `geometry.py:gold_volume × density` hits the target. A miss fills `Solved` via `solve_failure`; if every variant misses, the closest miss binds and alternatives are pooled.
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
| `core/result.py` | `JobResult` / `Infeasible` reply contract (Pydantic) | orchestrator |
| `core/lang.py` | Reply language detection (en / hinglish) | — |
| `core/transport.py` | Output channel (Console; Nonilion stub) | — |
| `packs/jewellery/schema.py` | `Brief`, `DesignSpec` (Pydantic) | — |
| `packs/jewellery/brief.py` | Sakhi: scope, questions, Brief (LLM + repair, regex fallback) | llm, lang, messages, sizes |
| `packs/jewellery/messages.py` | English + Hinglish reply templates | — |
| `packs/jewellery/sizes.py` | Indian ring size → inner diameter, bangle 2-N, US sizes | `data/ring_sizes.json` |
| `packs/jewellery/rates.py` | Gold rate set in chat | `data/gold_rates.json` |
| `packs/jewellery/designer.py` | Naqqash: variants | llm, schema |
| `packs/jewellery/pricing.py` | Jauhari: plan + quote | gold, `data/rate_card.json` |
| `packs/jewellery/dfm.py` | Casting rules (spec-level today) | schema |
| `packs/jewellery/geometry.py` | bpy/bmesh builders, volume. Rings: plain band (comfort/flat/knife/faceted), solitaire (4/6 claws), `motif="floral"` flower top (`floral_top`: seat + `petals` ellipsoid petals to `size_mm` flower diameter + bead or bezel-set stone); ring bands are built so the inscribed finger hole equals `inner_d_mm` | bpy |
| `packs/jewellery/mesh_check.py` | Topology hygiene of the gold (`check`: watertight, manifold, consistent outward normals, 1 component, no self-intersections > 1 µm) and `ring_inner_diameter` measured on the mesh. Used by tests today | bpy |
| `packs/jewellery/render.py` | Studio, Cycles, STL/GLB | bpy |
| `packs/hardware` | Roadmap placeholder | — |

## External services
- LLM (`core/llm.py:complete_json`), optional. Backend from `KARIGAR_LLM_BACKEND` (auto/agentrouter/anthropic/none), config from `.env`:
  - `agentrouter`: subprocess `claude -p … --tools "" --append-system-prompt` with `ANTHROPIC_BASE_URL=https://agentrouter.org`; prompt on stdin; timeout `KARIGAR_LLM_TIMEOUT_S`.
  - `anthropic`: Anthropic SDK.
  - Any failure → None → caller uses its deterministic path (`brief._regex_parse`, `designer.fallback`). Brief JSON that fails validation gets one repair call first.
- Nonilion: no Bot API exists yet. `NonilionTransport` stays a stub; Nonilion reaches Karigar as an imported OpenAI-compatible service (Phases 6.5–8).
