# Status / resume point
Updated 2026-11-14. Read this first when resuming.

**2026-11-14 run (attended)**: venv rebuilt (Python 3.13 + bpy 5.3.0, the old one was zero-filled); every automated gate item of Phases 0–10 is done and tested; what is left is manual and the user's.

## Phases
| Phase | Status | Left (who) |
|---|---|---|
| 0 Baseline + test harness | done | — |
| 0.5 Blender MCP | done (manual items approved 2026-11-13) | — |
| 1 Scope + data contracts | done | — |
| 2 Ring families | done | — |
| 2.5 Design catalogue (19) | done | — |
| 3 Weight + solver honesty | done | — |
| 4 Mesh checks | done | — |
| 5 Quote + rate + package | done | — |
| 6 Order store + edits | done | — |
| 6.5 Nonilion probe | answers recorded | user: formal tick of the two manual items |
| 7 Service + worker | automated done | user: deploy on Render, redeem credits |
| 8 Nonilion room | automated done (setup doc, instruction texts, injection tests) | user: import Sakhi + Karigar, live room checks |
| 8.5 Sim + security | sim pass (docs/user-sim-report.md), backlog cleared | user: security-breaker full run (skill not installed here) |
| 9 Demo readiness | demo inputs listed + tested, weight proof, budget | user: rehearse 6-min flow, record backup video |
| 10 Web console | all 8 pages built, API tested, live-checked over HTTP | user: look in a browser (phone + desktop), `impeccable` + `hallmark` pass, screenshots into docs/ |

## Repo state
- Never committed by Claude (user commits). New since af89194: `sim/`, `console/`, `nonilion/`, `scripts/make_catalogue.py`, `docs/{nonilion-setup,user-sim-report,weight-proof}.md`, `.gitattributes`, tests `test_injection_phase8.py`, `test_security_backlog.py`, `test_weight_proof_bpy.py`, `test_console_api.py`.
- Gate: `.claude/test-command`. Last full run 2026-11-14: 1110 passed, 0 failed (12 min 53 s).
- `data/gold_rates.json` was refreshed from MCX on 2026-11-14 (real rate, git-ignored).
