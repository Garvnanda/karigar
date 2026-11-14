# User simulation report (Phase 8.5)

Run 2026-11-14 on the laptop (WSL, bpy 5.3.0, LLM off): `./venv/bin/python -m sim.run --users 1000 --solve-every 5`.
Users and input mix: `sim/users.py` (seed 7). Harness: `sim/run.py`. Writes only to a temp dir.

## Pass bar (set here; the `user-sim` skill's reference.md is not in this repo)
| Measure | Bar | Result |
|---|---|---|
| Crashes / unhandled exceptions | 0 | **0** |
| Valid-input error rate (order, partial, out-of-scope, rate) | < 1% | **0.0%** |
| Invalid inputs rejected correctly (never become a brief) | 100% | **100%** (200/200) |
| p95 counter reply (intake + plan, no bpy) | ≤ 0.5 s | **0.009 s** |
| p95 one design solved + mesh-checked | ≤ 30 s | **5.6 s** (91 solves) |

Mix: 470 orders, 186 partial (asks a question), 80 out of scope, 64 chat rate messages (no sender), 200 invalid
(empty, emoji, 2,000+ chars, signs/exponents, size 0/99/12.5, NUL bytes, HTML/SQL, nested braces, Devanagari, ₹10¹¹ budgets).

## Failure clusters and fixes
1. **Old piece read as the new piece** (first run: 50 of 470 orders, 10.6%). "old 13.2g 14K bangle exchange" + a pendant/jhumka/coin
   order was read as a bangle, so the bangle size was asked. Root cause: `brief._regex_parse` took the first piece word by
   priority, and only chains were treated as the old-gold source. Fix: the first piece word after each "old / purani / nani …"
   word is the old piece and is skipped when another piece is named. Test: `tests/test_security_backlog.py::test_sim_old_gold_piece_is_not_the_piece_to_make`.

## Not failures
24 of the 91 solved orders came back infeasible, each naming its binding rule (e.g. "maximum sensible proportions of the Phool
Nosepin design" for a 12.8 g nose pin, "minimum ring shank thickness 1.5 mm" for a 3.5 g size-22 ring). The generator picks
random weights/budgets (2.5–14 g, ₹40k–3 lakh) without regard to the piece, so these are correct refusals.

## Not covered
Renders (measured separately, decisions.md), the LLM path (tests use fakes; the demo runs without it), and HTTP-level load on
the Render service (covered by the concurrency tests in `tests/test_service_core.py` / `test_service_http.py`).
