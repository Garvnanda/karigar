# Questions for the user
Unchecked items block build-all and scheduled runs. Answer under the item, then tick it.

- [x] (All phases, blocker) Unattended runs can't run the test gate — the `.claude/test-command` (`wsl -e bash -lc "cd … && ./venv/bin/python -m pytest -q"`) needs permission approval, and no allow rule covers `wsl`. Without it no phase can be verified (2026-11-12 run stopped here). Options: (a) add an allow rule for exactly that command (e.g. `Bash(wsl -e bash -lc "cd /mnt/c/Users/harag/Documents/coding/igdtuw/karigar/karigar && ./venv/bin/python -m pytest*)`) in the project's `.claude/settings.json`; (b) run build-all attended so you can approve each run.
  **Answer**: (a) Allow rule added to `.claude/settings.json` for exactly the test command (2026-11-13).
- [x] (Phase 1, security F2, high) Who may set the gold rate? docs/security/1.md F2: any message like "aaj ka rate 22K 14730" from anyone in the room sets the rate; intake has no sender. Options: (a) only Sakhi's configured owner/staff IDs may set it (needs sender identity — depends on what Nonilion sends, Phase 6.5); (b) chat-set rates need a confirmation step ("Rate 14730 set? reply haan"); (c) accept the risk for P0 (demo room is private) and record it in decisions.md.
  **Answer**: (a) Only configured owner/staff IDs may set the rate (2026-11-13). Sender identity depends on what Nonilion sends (Phase 6.5); until known, chat rates from an unknown sender are rejected and the config rate applies.
- [x] (Phase 1, security F9, high) Customer-claimed purity ("tested 99.9%") still overrides the karat's purity for the old-gold credit (`brief.py:168`, `gold.py:67`), and the LLM may fill `tested_purity`. Docs/security/1.md marked it "needs user decision" but it never reached this file. Options: (a) ignore claimed purity; credit at the stated karat only; (b) accept a tested purity only from a code-parsed "XRF/touch test" phrase, capped at the karat's purity + 0.5%, shown as "customer-stated"; (c) accept the risk.
  **Answer**: (a) Ignore claimed purity; credit old gold at the stated karat's purity only (2026-11-13).

- [x] (Phase 8) Nonilion API / how agents reach our code?
  **Answer**: No API yet ("Soon"). Import → Other takes a key + OpenAI-compatible base URL + instructions; Karigar is that service (docs/nonilion.md).
- [x] (Phase 1) Piece scope — keep bangles?
  **Answer**: Keep bangles (ring, bangle, pendant).
- [x] (Phase 3/4) Caster numbers?
  **Answer**: Use sourced defaults, cited and labelled "assumed" (decisions.md "Shop numbers").
- [x] (Phase 5) Old-gold deduction, hallmark, GST, making?
  **Answer**: 2% deduction; hallmark ₹75 (BIS rate since 14 Sep 2026; user picked ₹45, which is out of date); GST 3% gold + 5% making (custom piece, per PKC India); making charge 3.5%.
- [x] (Phase 1) Ring size table?
  **Answer**: Standard published Indian chart, cited.
- [x] (Phase 7) Hosting / worker?
  **Answer**: Worker on the user's laptop (Intel integrated GPU). Render has no GPUs; Render hosts the thin service, laptop polls it; rent a GPU for demo day only if renders are too slow. Budget ≤ $50 (decisions.md "Hosting").
- [x] (Phase 8) How many agents?
  **Answer**: Two: Sakhi + Karigar.
- [x] (Phase 1) Reply language?
  **Answer**: Mirror the jeweller.
- [x] (Phase 5) Gold rate source?
  **Answer**: Chat + config, timestamped, 24 h staleness.
- [x] (Phase 0.5) Blender desktop?
  **Answer**: Not installed; user installs 5.x. MCP server scanned before install.
- [x] (Phase 9) Real pieces for weight proof?
  **Answer**: None. Prove volume maths against exact formulas + show calibration.
- [x] (Phase 9) When is judging / the submission deadline?
  **Answer**: No date given; "a bit short on time — complete as soon as possible and submit" (2026-11-11). Build P0 phases in order, no extras.
- [x] (Phase 2.5) Design catalogue depth and styles?
  **Answer**: Full engine families; starred shortlist (2026-11-13): rings floral cluster, three-stone, halo solitaire, butterfly; pendants heart halo, paisley, temple lotus; rope + curb chains; 10 g lotus coin; bangles temple kada, twisted rope, leaf-vine; earrings jhumka, chandbali, floral stud, bali hoop; flower nosepin; convertible screw-back stud. Original designs, no brand copies.
- [x] (All phases) Security breaking per phase?
  **Answer**: No. Only the phase's tests + phase-reviewer per phase; one full security-breaker run at the end (Phase 8.5) (2026-11-13).
- [x] (Phase 2.5) Minimum finished weight for chain, coin, earring pair, nosepin? Docs silent; today no minimum is enforced (a 0.5 g chain is accepted).
  **Answer**: No fixed gram minimum; Phase 4 mesh checks (wall, link, post thickness) refuse anything too thin to cast and name the thin part (2026-11-13).
- [x] (Phase 2.5) Default stone size when a customer names a stone but no size, for earrings / nosepins? Docs silent; today 0 ct for budget planning (stone cost ignored), family's own stone used in the build.
  **Answer**: Use the design's own stone size, priced from the rate card; quote says 'stone size assumed: X' (2026-11-13).
- [x] (Phase 2.5) Necklace request: nearest supported piece is still "pendant" (2026-11-11). Switch to "chain" now chains are in scope?
  **Answer**: Suggest chain + pendant (2026-11-13). Supersedes the 2026-11-11 'pendant' rule.
- [x] (Phase 2.5) Keep "lotus pendant" → temple lotus design and plain "kada" → temple kada? Replaces the original lotus pendant / plain kada for those words (incl. README e2e lotus-pendant order).
  **Answer**: Yes: 'lotus pendant' → pendant_temple_lotus, plain 'kada' → bangle_temple_kada; README lotus-pendant order re-solves on the new design (2026-11-13).
- [x] (Phase 5/7) Gold-rate worker job: which website exactly (URL)? Is MCX price per 10 g of 24K (999)? Does +₹5,000 apply per 10 g? How are 22K/18K/14K derived (× purity 0.916/0.75/0.585)? How often should the job run?
  **Answer**: MCX + ₹5,000 (user). Rest assumed per decisions.md 2026-11-13 "Build-all runs without pausing": per 10 g 24K, karats × purity, every 6 h, site picked in Phase 5 — change if wrong.
- [ ] (Phase 3/4) Ornament wall floor: earrings/nose ornaments use 0.6 mm (jhumka bell, stud plate, filigree wire; nose petals 0.5, chain wire 0.5) while the sourced general wall minimum is 0.8 mm. Keep 0.6 for these small ornaments (assumed, current) or raise all to 0.8 (heavier earrings/nose pins)?
  **Answer**: (assumed 0.6 until answered)
