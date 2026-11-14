"""Phase 3 — weight and solver honesty, the parts that need no Blender: densities and casting
minimums from data/casting.json, the tolerance band, the weights every result reports, the
solver's acceptance window and iteration cap, and the infeasible contracts' wording."""
import json
import statistics

import pytest

from karigar.core import gold as G
from karigar.core.calibration import CalibrationStore
from karigar.core.registry import Plan, Solved
from karigar.core.solver import ACCEPT_ABS, ACCEPT_REL, MAX_ITER, SolveResult, accept_window, solve_monotone
from karigar.packs.jewellery import designer, dfm, job_card, jobcard, pricing, solve_failure, stone_too_big
from karigar.packs.jewellery.schema import Brief, DesignSpec

CFG = json.loads(G.CASTING_FILE.read_text(encoding="utf-8"))


# ----------------------------------------------------------- density from config
def test_density_comes_from_the_config_file_with_the_sourced_values():
    assert not hasattr(G, "DENSITY")                       # no code constant left
    assert CFG["density_g_cm3"] == {"24": 19.32, "22": 17.75, "18": 15.45, "14": 13.05}  # "Shop numbers"
    for k in (24, 22, 18, 14):
        assert G.density(k) == CFG["density_g_cm3"][str(k)]
    assert G.mm3_to_grams(1000.0, 22) == pytest.approx(17.75)


def test_a_shop_edit_to_the_config_changes_the_weight(tmp_path, monkeypatch):
    cfg = {**CFG, "density_g_cm3": {**CFG["density_g_cm3"], "22": 18.0}}
    p = tmp_path / "casting.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(G, "CASTING_FILE", p)
    assert G.mm3_to_grams(1000.0, 22) == pytest.approx(18.0)
    assert G.grams_to_mm3(18.0, 22) == pytest.approx(1000.0)


def test_unconfigured_karat_is_refused_not_guessed():
    with pytest.raises(ValueError):
        G.density(10)


# ----------------------------------------------------------- DFM minimums
def test_dfm_minimums_are_the_sourced_values():
    assert CFG["dfm_min_mm"] == {"ring_shank": 1.5, "wall": 0.8, "prong_d": 0.8}
    assert dfm.MIN_SHANK == 1.5 and dfm.RULES["ring"]["min_thickness"] == 1.5
    assert dfm.MIN_WALL == 0.8 and dfm.RULES["pendant"]["min_thickness"] == 0.8
    assert dfm.PRONG_D == 0.8


def test_ring_cannot_go_below_a_1_5_mm_shank():
    spec = DesignSpec(name="b", piece_type="ring", width_mm=3.0, thickness_mm=1.8)
    lo, _ = dfm.scale_bounds(spec)
    assert spec.thickness_mm * lo == pytest.approx(1.5)
    assert dfm.binding_rule(spec, "lo") == "minimum ring shank thickness 1.5 mm"


def test_catalogue_ring_shank_bottom_never_below_1_5_mm():
    from karigar.packs.jewellery import families
    from karigar.packs.jewellery.families.rings import TAPER_T
    for fam in families.for_piece("ring"):
        for lab in families.LABELS:
            spec = DesignSpec(**{**fam.variant_fields(lab), "name": "x", "piece_type": "ring", "family": fam.name})
            lo, hi = dfm.scale_bounds(spec)
            assert lo <= hi, (fam.name, lab)
            assert spec.thickness_mm * lo * TAPER_T >= 1.5 - 1e-9, (fam.name, lab)


def test_pendant_wall_never_below_0_8_mm():
    spec = DesignSpec(name="p", piece_type="pendant", size_mm=18, thickness_mm=1.2)
    lo, _ = dfm.scale_bounds(spec)
    assert spec.thickness_mm * lo >= 0.8 - 1e-9


# ----------------------------------------------------------- tolerance
def test_tolerance_default_until_enough_records():
    t = G.tolerance([])
    assert t["pct"] == CFG["tolerance"]["default_pct"] and t["assumed"]
    assert G.tolerance([3.0, 3.5])["pct"] == CFG["tolerance"]["default_pct"]   # < min_records


def test_tolerance_from_the_workshops_recorded_loss_spread():
    losses = [2.0, 3.0, 4.0, 3.5]
    t = G.tolerance(losses)
    assert not t["assumed"]
    assert t["pct"] == pytest.approx(CFG["tolerance"]["sigma"] * statistics.stdev(losses), abs=1e-3)
    assert G.tolerance([3.0, 3.0, 3.0])["pct"] == CFG["tolerance"]["floor_pct"]   # identical: floor


def test_calibration_store_tolerance_uses_its_records(tmp_path):
    c = CalibrationStore(tmp_path / "c.json")
    assert c.tolerance("w1")["assumed"]
    for d, a in ((10.0, 9.7), (10.0, 9.6), (10.0, 9.75)):
        c.record("w1", d, a)
    t = c.tolerance("w1")
    assert not t["assumed"] and t["pct"] == pytest.approx(max(0.5, 2 * statistics.stdev([3.0, 4.0, 2.5])), abs=1e-3)
    assert c.tolerance("other")["assumed"]


# ----------------------------------------------------------- weights every result reports
def _plan(**detail):
    return Plan(True, target_value=7.84, detail={"casting_loss_pct": 3.0, **detail})


def test_weights_report_finished_casting_loss_and_tolerance():
    w = pricing.weights(7.84, _plan())
    assert w["casting_g"] == 7.84 and w["finished_g"] == pytest.approx(7.605, abs=1e-3)
    assert w["expected_loss_g"] == pytest.approx(0.235, abs=1e-3) and w["expected_loss_pct"] == 3.0
    assert w["tolerance_g"] == pytest.approx(round(7.6048 * 0.04, 2))
    assert pricing.weight_text(w).startswith("7.60 g ± 0.30 g finished (cast 7.84 g")


def test_weights_use_the_workshop_tolerance_when_the_plan_has_it():
    w = pricing.weights(7.84, _plan(tolerance={"pct": 1.0, "source": "x", "assumed": False}))
    assert w["tolerance_pct"] == 1.0 and w["tolerance_g"] == pytest.approx(0.08, abs=0.005)


def test_quote_and_job_card_show_the_tolerance(tmp_path):
    p = pricing.plan(Brief(piece_type="ring", karat=22, target_weight_g=6.0), 3.0)
    assert p.ok and p.detail["tolerance"]["pct"] == CFG["tolerance"]["default_pct"]
    spec = DesignSpec(name="Band", piece_type="ring")
    brief = Brief(piece_type="ring", karat=22, target_weight_g=6.0)
    q = pricing.quote(spec, p.target_value, brief, p)
    w = q["weights"]
    assert {"casting_g", "finished_g", "expected_loss_g", "tolerance_g"} <= set(w)
    assert f" g ± {w['tolerance_g']:.2f} g finished (cast {w['casting_g']:.2f} g" in q["summary"]
    job = job_card(spec, Solved(spec, True, 1.0, p.target_value, p.target_value, 4), brief, p, {}, 1,
                   pricing.rate_card())
    assert job["casting_weight_g"] == w["casting_g"] and job["tolerance_g"] == w["tolerance_g"]
    md = jobcard.job_card_md(job, {}, tmp_path)
    assert f"± {w['tolerance_g']:.2f} g" in md and "Tolerance: ±4% — default" in md


def test_pack_weights_is_what_results_report():
    from karigar.packs.jewellery import PACK
    spec = DesignSpec(name="Band", piece_type="ring")
    w = PACK.weights(Solved(spec, True, 1.0, 5.0, 5.0, 3), _plan())
    assert w == pricing.weights(5.0, _plan())


# ----------------------------------------------------------- solver window and cap
def test_accept_window_is_the_tighter_of_0_1_g_and_2_pct():
    assert (ACCEPT_ABS, ACCEPT_REL) == (0.1, 0.02)
    assert accept_window(2.0) == pytest.approx(0.04)          # 2% of 2 g
    assert accept_window(34.0) == pytest.approx(0.1)          # 0.1 g on a kada
    assert accept_window(1000.0, accept_abs=None) == pytest.approx(20.0)


@pytest.mark.parametrize("target", [0.25, 1.3, 4.0, 9.7, 18.0, 34.0])
def test_solver_lands_within_the_window_under_the_cap(target):
    f = lambda s: 5.0 * s ** 2.3 + 0.2 * s
    r = solve_monotone(f, target, 0.2, 3.0)
    assert r.ok and abs(r.value - target) <= accept_window(target)
    assert len(r.iterations) <= MAX_ITER + 2


def test_solver_stops_at_the_iteration_cap_and_says_so():
    calls = []

    def stairs(s):              # monotone but jumps over the target: never converges
        calls.append(s)
        return 1.0 if s < 1.234567 else 3.0
    r = solve_monotone(stairs, 2.0, 0.5, 2.0)
    assert not r.ok and r.reason == "no_convergence"
    assert len(calls) == MAX_ITER + 2


# ----------------------------------------------------------- infeasible contracts
def test_below_min_and_above_max_name_the_binding_rule():
    spec = DesignSpec(name="b", piece_type="ring", width_mm=3.0, thickness_mm=1.8)
    lo = solve_failure(SolveResult(False, 0.83, 3.0, 1.0, [], "below_min"), 3.0, spec)
    assert lo["binding_constraint"] == "minimum ring shank thickness 1.5 mm"
    assert lo["best_achievable"] == {"value": 2.91, "unit": "g"} and len(lo["alternatives"]) >= 2
    hi = solve_failure(SolveResult(False, 1.94, 12.0, 20.0, [], "above_max"), 3.0, spec)
    assert hi["binding_constraint"] == "maximum ring shank thickness 3.5 mm"
    assert hi["best_achievable"]["value"] == pytest.approx(11.64) and len(hi["alternatives"]) >= 2


def test_stone_too_big_offers_the_largest_stone_the_design_holds():
    spec = DesignSpec(name="s", piece_type="ring", width_mm=2.0, thickness_mm=3.0, gem="diamond", gem_d_mm=12.0)
    lo, hi = dfm.scale_bounds(spec)
    assert lo > hi
    f = stone_too_big(spec, lo)
    d = dfm.max_stone_d(spec)
    assert 0 < d < 12.0
    assert dfm.scale_bounds(spec.model_copy(update={"gem_d_mm": d}))[0] <= hi    # it really fits
    assert f["best_achievable"]["unit"] == "ct" and f["best_achievable"]["value"] > 0
    assert "stone" in f["binding_constraint"] and len(f["alternatives"]) >= 2


# ----------------------------------------------------------- coin stamp
def test_coin_stamp_is_the_briefs_target_weight():
    b = Brief(piece_type="coin", karat=22, target_weight_g=8.0)
    assert {s.params["stamp_g"] for s in designer.propose(b, 0.0)} == {8.0}
    b = Brief(piece_type="coin", karat=22, budget_inr=90000)
    assert {s.params["stamp_g"] for s in designer.propose(b, 0.0)} == {designer.COIN_STAMP_G} == {10.0}


def test_budget_plan_without_stone_size_marks_a_joint_solve():
    b = Brief(piece_type="ring", karat=18, budget_inr=60000, gem="diamond", ring_inner_d_mm=17.2)
    p = pricing.plan(b, 3.0)
    assert p.ok and p.detail["joint_stone"] and p.detail["budget_inr"] == 60000
    fixed = pricing.plan(b.model_copy(update={"gem_ct": 0.5}), 3.0)
    assert fixed.ok and "joint_stone" not in fixed.detail          # a named stone stays fixed


def test_below_minimum_plan_reports_the_minimum_not_the_request():
    p = pricing.plan(Brief(piece_type="ring", karat=22, target_weight_g=1.0), 3.0)
    assert not p.ok and p.best_achievable == {"value": 1.8, "unit": "g"}


def test_job_card_warns_when_the_seats_are_left_to_the_setter():
    spec = DesignSpec(name="S", piece_type="ring", gem="ruby", gem_d_mm=3.0)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=5.0, gem="ruby", gem_ct=0.15)
    args = (spec, Solved(spec, True, 1.0, 5.0, 5.0, 3), brief, _plan(), {}, 1, pricing.rate_card())
    assert not any("seats are NOT cut" in w for w in job_card(*args)["warnings"])
    assert any("seats are NOT cut" in w for w in job_card(*args, seats_in_model=False)["warnings"])


# ----------------------------------------------------------- budget: never over after rounding
def test_budget_step_down_finds_a_scale_within_the_budget():
    from karigar.packs.jewellery import JewelleryPack
    total = lambda s: 1000.0 * s                     # rises with the scale
    s = JewelleryPack._fit_budget(total, 900.0, 0.5, 1.0)   # 20 x 0.1% steps are not enough
    assert s is not None and total(s) <= 900.0 and total(s) > 899.0


def test_budget_step_down_returns_none_when_even_the_lightest_tops_the_budget():
    from karigar.packs.jewellery import JewelleryPack
    assert JewelleryPack._fit_budget(lambda s: 1000.0 + s, 900.0, 0.5, 1.0) is None
