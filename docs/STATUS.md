# Status / resume point
Updated 2026-11-11. Read this first when resuming.

## Phases
| Phase | Status | Notes (what's left, who) |
|---|---|---|
| 0 Baseline + test harness | done | Reviewer PASS 2026-11-11. 69 tests; golden weights, README orders e2e, render timing in decisions.md |
| 0.5 Blender MCP (dev tool) | manual | Installed Blender 5.3 + official MCP add-on + server (`.mcp.json`). Left: user builds a ring live + screenshot (testing.md "Your manual checks") |
| 1 Scope + data contracts | todo | All questions answered; next to build |
| 2 Ring families | todo | Motif (floral) ring missing — blocks Hero A |
| 3 Weight + solver honesty | todo | Tolerance display, binding-constraint naming, joint budget solve |
| 4 Mesh checks | todo | `dfm.py` checks spec, spec requires mesh checks |
| 5 Quote + rate + package | todo | Stale-rate handling, hallmarking, buyback deduction, MD job card |
| 6 Order store + edits | todo | Nothing exists |
| 6.5 Nonilion probe | todo | Tiny OpenAI-compatible logger; import as "Other" to learn what Nonilion sends. Do early |
| 7 OpenAI-compatible Karigar + worker | todo | Shape depends on 6.5 findings |
| 8 Nonilion room setup | todo | Import → Other per agent; see docs/nonilion.md |
| 8.5 User simulation | todo | — |
| 9 Demo readiness | todo | — |

## Pending before/at resume
1. Build-all running (2026-11-11). Next: Phase 1 (scope + data contracts). Phase 6.5 probe builder running in parallel (stdlib only, `probe/`).
2. Manual steps for the user, collected in testing.md "Your manual checks": Blender MCP live check (0.5); later probe import into Nonilion (6.5), Render deploy (7), live room (8), demo video (9).

## Repo state
- No commits yet. Build work staged (`git add`), never committed. `brag-output/` (promo video plan from another session) left unstaged. No remote.
- Registered in ~/.claude/workflow/projects.md as `on` (plan approved 2026-11-11).
- Gate: `.claude/test-command` → 69 passed excluding in-progress `tests/test_probe.py` (2026-11-11, Phase 0).
