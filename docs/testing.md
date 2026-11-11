# Testing guide

## Automated
- Full suite: `.claude/test-command` — runs `pytest -q` inside WSL with the project venv. 69 tests, ~75 s (most of it the bpy and end-to-end tests).
- Setup once (in WSL): `./venv/bin/pip install -r requirements.txt`.
- Covered: `gold.py` targets, `solver.py` convergence + bounds, `calibration.py` (temp files), `pricing.py` plan + quote (incl. old-gold credit), `brief.py` regex parser.
- `tests/test_geometry_bpy.py` — golden gold weights: plain ring, solitaire ring, beaded bangle, lotus pendant at fixed scales must match `tests/golden/gold_volume.json` to 0.01 g and be identical across two builds in one process. Regenerate only after an intended geometry change: `KARIGAR_REGEN_GOLDEN=1 ./venv/bin/python -m pytest -q tests/test_geometry_bpy.py` ; a missing file or key fails the test. Review the JSON diff before staging.
- Phase 2 (bpy, ~35 s): `tests/test_ring_families_bpy.py` builds 8 ring families (bands comfort/flat/knife/faceted, solitaire 4/6, floral, floral with stone) × scales 0.8/1.0/1.35 and asserts each gold body passes `mesh_check.check` (watertight, manifold, consistent outward normals, one component, no self-intersection) and that the inner diameter measured on the mesh is within ±0.05 mm of `inner_d_mm`; plus floral parameters (petal count, flower size, scales with ring), monotone volume in scale. `tests/test_mesh_hygiene_bpy.py` proves the checker catches each defect on known-bad meshes (open, two pieces, inside-out, one flipped face, crossing solids incl. a 0.01 mm crossing) and that inner diameter is the inscribed circle, not the nearest vertex.
- Manual mesh look (optional): export a floral ring STL via a CLI order and open it in Blender; the flower should sit on top of the band, nothing inside the finger hole.
- `tests/test_render_bpy.py` — every gem and metal material builds on the pinned bpy.
- Phase 1 (no bpy, ~2 s): `test_brief.py` (scope reply, language mirroring, question policy, ambiguous style → 3 variants, LLM repair with a fake `complete_json`), `test_sizes.py` (each Indian size 1–30 through `Brief(ring_size=…)`), `test_lang.py`, `test_rates.py` (rate parse/store/ack, temp `RATES_FILE` from conftest), `test_result.py` (JobResult contract, infeasible payloads from plan + solver, all-variants-fail pooling with a fake pack), `test_scripted_briefs.py` (12 scripted briefs in `tests/data/briefs.json`, including heroes A–D).
- `tests/conftest.py` also points `rates.RATES_FILE` at a temp file, so tests never write `data/gold_rates.json`.
- `tests/test_orders_e2e.py` — the 5 README orders through `Orchestrator.handle` at `draft`, 3 variants, into `tmp_path`, with a temp `CalibrationStore` (`Orchestrator(calibration=...)`). Asserts status (done / done / done / infeasible / needs_info) and, for done orders, `casting.stl`, `model.glb`, `job_card.json`, `quote.json`, `render_hero.png` per variant plus `order.json`.
- `tests/test_probe.py` — Phase 6.5 probe: server on an ephemeral port in a thread; auth 401/200, models (with and without `/v1`), health, 404, non-stream chat.completion shape and echoed findings, SSE chunks + `[DONE]`, `include_usage`, delay/stream directives and env defaults, log fields, redaction (key, cookie, token headers, body `api_key`), data-URI images logged as type+length, truncation, `/probe/log` auth, `python -m probe` from env. Security round (docs/security/6.5.md, one or more tests per finding): unauthenticated bodies not parsed (spy) and huge declared bodies answered 401 without reading; 413 / JSON node and depth caps; log line cap, multi-file rotation and backward `tail()`; lone surrogate, huge directive numbers, wrong field types, catch-all 500 with no traceback; secrets in path/query/keys/headers; read timeout (raw half-sent socket), 429 slow-reply cap, 503 connection cap; U+2028 entries; last X-Forwarded-For hop; `/<agent>/v1` paths and bad slugs → 404. ~8 s.
- `tests/conftest.py` unsets `ANTHROPIC_API_KEY` / `AGENTROUTER_API_KEY` and sets `KARIGAR_LLM_BACKEND=none` for every test, so tests never call a real model. `tests/test_llm.py` drives the AgentRouter path with a fake `subprocess.run`.

### Live AgentRouter check (manual)
1. `cp .env.example .env`, set `AGENTROUTER_API_KEY`.
2. In WSL: `./venv/bin/python -c "from karigar.core import llm; print(llm.backend(), llm.complete_json('Extract piece_type as JSON.', 'mujhe ek sone ki anguthi chahiye'))"` — expected: `agentrouter {'piece_type': 'ring'}` and an `(llm) agentrouter … ok in Ns` line on stderr. A timeout or error prints a reason and `None`.

## Manual (live)
### CLI orders (run in WSL from the repo root)
1. `./venv/bin/python run.py order "Nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai, size 2-6" --quality draft` — expected: `status: done`, `out/ORD-…/v1..v3/` with renders, `casting.stl`, `model.glb`, `job_card.json`, `quote.json`.
2. `./venv/bin/python run.py order "18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 12" --quality draft` — expected: `done`.
3. `./venv/bin/python run.py order "purani 22K chain 6.2g se 22K ruby lotus pendant banao" --quality draft` — expected: `done`.
4. `./venv/bin/python run.py order "18K 1 ct diamond ring under 10k, size 12"` — expected: `infeasible`, with options.
5. `./venv/bin/python run.py order "kuch sundar sa bana do"` — expected: `needs_info`, up to 3 questions in Hinglish in one reply.
5a. `./venv/bin/python run.py order "22K ring of 6g"` — expected: `needs_info`, asks for the ring size (no assumed size).
5b. `./venv/bin/python run.py order "aaj ka rate 22K 14730"` — expected: `rate_set`, a Hinglish acknowledgement with the time. (Writes `data/gold_rates.json`; delete it afterwards.)
5c. `./venv/bin/python run.py order "I want a 22K necklace, 20 g"` — expected: `out_of_scope`, offers a pendant.
6. `./venv/bin/python run.py calibrate --workshop test-01 --designed 18.58 --actual 17.95` — expected: learned loss ≈ 3.39%. (Writes `data/calibration.json`; delete it afterwards.)

### Visual checks
- Open `casting.stl` / `model.glb` in a viewer: one solid, correct ring size, no floating parts.

### Blender MCP (dev tool, Phase 0.5)
Installed: Blender 5.3.0 desktop (`C:\Program Files\Blender Foundation\Blender 5.3`), the official Blender Lab MCP add-on (`bl_ext.user_default.mcp`, enabled), and the MCP server `blender-mcp.exe` (uv tool, pinned commit `dbbf836`). Registered in the project's `.mcp.json` as server `blender`.
1. Start Blender with online access: `"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --online-mode` (or Preferences → System → Allow Online Access).
2. In Blender: Sidebar/N-panel or Preferences → Add-ons → MCP → **Start** the bridge (listens on `localhost:9876`).
3. Restart Claude Code in this repo and approve the `blender` MCP server when asked. `/mcp` should list it as connected.
4. Ask Claude to build a ring in the scene, e.g. "import karigar's DesignSpec ring at scale 1.0 into the open Blender scene and take a viewport screenshot" — expected: a ring appears and a screenshot comes back.
Note: desktop is 5.3.0; the pipeline's bpy wheel is 5.0.1. The MCP is for viewing/debugging only.

### Nonilion probe (Phase 6.5)
Local: `PROBE_API_KEY=test123 python -m probe`, then
`curl -H "Authorization: Bearer test123" localhost:8080/v1/models`,
`curl -N -H "Authorization: Bearer test123" -H "Content-Type: application/json" -d '{"model":"x","stream":true,"messages":[{"role":"user","content":"probe stream 5 probe delay 5"}]}' localhost:8080/v1/chat/completions`,
`curl -H "Authorization: Bearer test123" "localhost:8080/probe/log?n=5"`.
Deploy + Nonilion import: README "Nonilion probe". Record every answer in docs/nonilion.md "Unknowns about the Other route".

## Your manual checks
- **(Phase 6.5)** Probe on Render over HTTPS; imported into a Nonilion room as "Other"; "Test the key" passes; every unknown in docs/nonilion.md answered (README "Nonilion probe" steps 1–6).
- **(Phase 0.5)** Steps 1–4 above: ring built in live Blender from a `DesignSpec`, viewport screenshot returned.

## Test data / accounts
- `data/rate_card.json` holds SAMPLE rates only.
- `.env` (from `.env.example`) holds `AGENTROUTER_API_KEY`; optional — without it the deterministic fallbacks run.

## Known gaps
- Gem dispersion is not rendered on bpy 5.0.1 (the wheel exposes no dispersion socket); check diamond renders by eye.
- Nonilion not wired yet; live room tests come with Phases 6.5–8.
