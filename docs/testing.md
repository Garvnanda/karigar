# Testing guide

## Automated
- Full suite: `.claude/test-command` — runs `pytest -q` inside WSL with the project venv. 69 tests, ~75 s (most of it the bpy and end-to-end tests).
- Setup once (in WSL): `./venv/bin/pip install -r requirements.txt`.
- Covered: `gold.py` targets, `solver.py` convergence + bounds, `calibration.py` (temp files), `pricing.py` plan + quote (incl. old-gold credit), `brief.py` regex parser.
- `tests/test_geometry_bpy.py` — golden gold weights: plain ring, solitaire ring, beaded bangle, lotus pendant at fixed scales must match `tests/golden/gold_volume.json` to 0.01 g and be identical across two builds in one process. Regenerate only after an intended geometry change: `KARIGAR_REGEN_GOLDEN=1 ./venv/bin/python -m pytest -q tests/test_geometry_bpy.py` ; a missing file or key fails the test. Review the JSON diff before staging.
- `tests/test_render_bpy.py` — every gem and metal material builds on the pinned bpy.
- `tests/test_orders_e2e.py` — the 5 README orders through `Orchestrator.handle` at `draft`, 3 variants, into `tmp_path`, with a temp `CalibrationStore` (`Orchestrator(calibration=...)`). Asserts status (done / done / done / infeasible / needs_info) and, for done orders, `casting.stl`, `model.glb`, `job_card.json`, `quote.json`, `render_hero.png` per variant plus `order.json`.
- `tests/test_probe.py` — Phase 6.5 probe: server on an ephemeral port in a thread; auth 401/200, models (with and without `/v1`), health, 404, non-stream chat.completion shape and echoed findings, SSE chunks + `[DONE]`, `include_usage`, delay/stream directives and env defaults, log fields, redaction (key, cookie, token headers, body `api_key`), data-URI images logged as type+length, truncation, `/probe/log` auth, `python -m probe` from env. ~3 s.
- `tests/conftest.py` unsets `ANTHROPIC_API_KEY` / `AGENTROUTER_API_KEY` and sets `KARIGAR_LLM_BACKEND=none` for every test, so tests never call a real model. `tests/test_llm.py` drives the AgentRouter path with a fake `subprocess.run`.

### Live AgentRouter check (manual)
1. `cp .env.example .env`, set `AGENTROUTER_API_KEY`.
2. In WSL: `./venv/bin/python -c "from karigar.core import llm; print(llm.backend(), llm.complete_json('Extract piece_type as JSON.', 'mujhe ek sone ki anguthi chahiye'))"` — expected: `agentrouter {'piece_type': 'ring'}` and an `(llm) agentrouter … ok in Ns` line on stderr. A timeout or error prints a reason and `None`.

## Manual (live)
### CLI orders (run in WSL from the repo root)
1. `./venv/bin/python run.py order "Nani ka purana 18.4g 22K kangan hai, naya beaded kada banana hai" --quality draft` — expected: `status: done`, `out/ORD-…/v1..v3/` with renders, `casting.stl`, `model.glb`, `job_card.json`, `quote.json`.
2. `./venv/bin/python run.py order "18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 6" --quality draft` — expected: `done`.
3. `./venv/bin/python run.py order "purani 22K chain 6.2g se ruby lotus pendant banao" --quality draft` — expected: `done`.
4. `./venv/bin/python run.py order "1 ct diamond ring under 10k"` — expected: `infeasible`, with options.
5. `./venv/bin/python run.py order "kuch sundar sa bana do"` — expected: `needs_info`, one follow-up question.
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
