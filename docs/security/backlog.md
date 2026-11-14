# Security backlog
Medium/low findings from security-breaker runs. Cleared in the User simulation phase.

- [x] [medium] Quadratic regex in probe JSON pre-scan freezes the process (`_JSON_STRING`, 64 KB body of `\"` → 8.7 s; key required) — 6.5 — docs/security/6.5.md#N3 — replace regex with one linear left-to-right scan tracking string state, depth and node count
- [x] [medium] Unauthenticated flood rotates real Nonilion entries out of the probe log (rest of F2) — 6.5 — docs/security/6.5.md#N4 — small fixed-size summaries for unauth requests, per-IP rate limit, authed entries in a separate file
- [x] [medium] `/probe/log?n=500` can return ~32 MB and use ~0.5 GB under concurrency (key required) — 6.5 — docs/security/6.5.md#N5 — cap total bytes returned (e.g. 4 MB) or return per-entry summaries
- [x] [medium] Deeply nested LLM JSON → RecursionError — 1 — docs/security/1.md#F10 — catch RecursionError in llm.extract_json (or pre-scan depth like probe/server._parse_json) and return None so the regex fallback runs
- [x] [medium] No input length cap; repair loop resends huge text — 1 — docs/security/1.md#F11 — cap message length at intake (e.g. 2,000 chars → needs_info) and cut text resent in the repair prompt
- [x] [medium] "within 2 weeks" read as ₹2 budget — 1 — docs/security/1.md#F12 — kbud regex rejects a number followed by a time unit; require ₹/rs/budget/k/lakh context for small numbers
- [x] [medium] No budget ceiling → 60 kg modelled target — 1 — docs/security/1.md#F13 — le= on budget_inr (e.g. ₹1 crore) or check planned weight against piece max proportions before solving
- [x] [medium] Ring size: 12.5 read as mm, size/mm conflicts silent, Brief(ring_size="12") → 17.3 default — 1 — docs/security/1.md#F14 — non-integer "size N" under 12 unreadable; ask when size and mm disagree; coerce numeric strings
- [x] [low] Signs/exponents dropped in weights (-10 g → 10, 1e9 g → 9) — 1 — docs/security/1.md#F15 — extend NUM lookbehind to exclude [-+e]; report such tokens as unreadable
- [x] [low] Stone carat missed after "22 carat" — 1 — docs/security/1.md#F16 — skip karat matches when searching for gem_ct
- [x] [low] Language detector mistakes (double "do", "Sona" as a name, Devanagari → en) — 1 — docs/security/1.md#F17 — weight ambiguous words; Devanagari → Hindi/Hinglish; handle proper names

Cleared 2026-11-14 (Phase 8.5), one reproducing test each in `tests/test_security_backlog.py` (N4 in `tests/test_probe.py`):
N3 string regex made linear (closing quote optional); N4 unauthenticated requests logged to `<log>.unauth` (1 MB, 1 old file); N5 `/probe/log` returns at most 4 MB; F10 RecursionError → None; F11 messages > 2,000 chars → needs_info `too_long` before parsing; F12 number + time unit is not a budget; F13 budget ≤ ₹1 crore; F14 "size 12.5" asked, `ring_size="12"` converts (size/mm conflict still takes the mm); F15 no sign/exponent around numbers; F16 gold "22 carat" never read as stone ct; F17 Devanagari → Hinglish (proper names not handled).
