"""Phase 4, bpy-free parts: grading, the rules config, the one relaxed retry, and the job card
wiring. The mesh measurements themselves are in test_meshdfm_bpy.py."""
import json

import pytest

from karigar.core.registry import Plan, Solved
from karigar.packs.jewellery import JewelleryPack, PACK, job_card, meshdfm, with_mesh
from karigar.packs.jewellery.jobcard import job_card_md
from karigar.packs.jewellery.meshdfm import FAIL, PASS, WARN, MeshDFM, RuleResult
from karigar.packs.jewellery.schema import Brief, DesignSpec

RING = DesignSpec(name="Band", piece_type="ring", karat=22, inner_d_mm=17.3, width_mm=3.0,
                  thickness_mm=1.8)
PLAN = Plan(True, target_value=4.0, detail={"casting_loss_pct": 3.0})


def _res(rule, status, measured, minimum, loc="6 o'clock"):
    sym = "<" if status == FAIL else "≥"
    return RuleResult(rule, status, measured, minimum, loc,
                      f"{rule} at {loc}: {measured} mm {sym} {minimum} mm", 10)


# ------------------------------------------------------------------ grading + config
@pytest.mark.parametrize("measured,status", [(1.40, FAIL), (1.50, WARN), (1.64, WARN), (1.66, PASS)])
def test_grade_fail_below_min_warn_within_10pct(measured, status):
    assert meshdfm.grade(measured, 1.5, 10) == status


def test_grade_measuring_tolerance_turns_a_faceting_shortfall_into_a_warning():
    # a 12-sided 0.8 mm wire measures 0.8 * cos(15 deg) = 0.773 mm flat to flat
    assert meshdfm.grade(0.773, 0.8, 10, tol_pct=4) == WARN
    assert meshdfm.grade(0.70, 0.8, 10, tol_pct=4) == FAIL


def test_rules_come_from_the_per_process_config_file():
    cfg = meshdfm.rules()
    assert meshdfm.RULES_FILE.name == "dfm_rules.json"
    assert cfg["min_mm"]["ring_shank"] == 1.5 and cfg["min_mm"]["wall"] == 0.8
    assert cfg["min_mm"]["prong_d"] == 0.8 and cfg["min_mm"]["chain_wire"] == 0.5
    assert cfg["min_mm"]["ornament_wall"] == 0.6 and cfg["min_mm"]["post_d"] == 0.8
    assert cfg["warn_margin_pct"] == 10


def test_rules_file_is_reread_when_edited(tmp_path):
    p = tmp_path / "rules.json"
    cfg = json.loads(meshdfm.RULES_FILE.read_text(encoding="utf-8"))
    p.write_text(json.dumps(cfg), encoding="utf-8")
    assert meshdfm.rules(p)["min_mm"]["wall"] == 0.8
    cfg["min_mm"]["wall"] = 1.1
    p.write_text(json.dumps(cfg), encoding="utf-8")
    import os
    st = os.stat(p)
    os.utime(p, (st.st_atime, st.st_mtime + 5))
    assert meshdfm.rules(p)["min_mm"]["wall"] == 1.1


def test_wall_minimum_per_family():
    cfg = meshdfm.rules()
    chain = DesignSpec(name="c", piece_type="chain", family="chain_rope", length_in=18)
    jh = DesignSpec(name="j", piece_type="earring", family="earring_jhumka")
    assert meshdfm.wall_min(chain, cfg) == (0.5, "chain_wire")
    assert meshdfm.wall_min(jh, cfg) == (0.6, "ornament_wall")
    assert meshdfm.wall_min(RING, cfg) == (0.8, "wall")


def test_clock_positions():
    from types import SimpleNamespace as P
    assert meshdfm.clock(P(x=0.0, z=-9.0)) == 6
    assert meshdfm.clock(P(x=0.0, z=9.0)) == 12
    assert meshdfm.clock(P(x=9.0, z=0.0)) == 3


def test_low_quantile_ignores_a_stray_short_ray_but_not_a_thin_part():
    vals = [1.6] * 199 + [0.1]
    assert meshdfm.low_quantile(vals, 0.02) == 1.6         # one grazing ray
    vals = [1.6] * 180 + [0.6] * 20                         # 10% of the part is thin
    assert meshdfm.low_quantile(vals, 0.02) == 0.6


# ------------------------------------------------------------------ relax
def test_generic_relax_makes_the_design_less_spread_out_never_thinner():
    rep = MeshDFM([_res("ring_shank", FAIL, 1.4, 1.5)])
    spec, what = meshdfm.relax(RING, rep)
    assert spec.width_mm == pytest.approx(3.0 * 0.85)
    assert spec.thickness_mm == RING.thickness_mm
    assert "width" in what


def test_generic_relax_drops_a_petal_on_a_lotus_pendant():
    p = DesignSpec(name="p", piece_type="pendant", shape="lotus", petals=8, size_mm=18)
    spec, what = meshdfm.relax(p, MeshDFM([_res("wall", FAIL, 0.6, 0.8)]))
    assert spec.petals == 7 and spec.size_mm == pytest.approx(18 * 0.85)


def test_relax_returns_none_when_nothing_can_shrink():
    tiny = DesignSpec(name="b", piece_type="ring", width_mm=1.0, size_mm=8.0)
    assert meshdfm.relax(tiny, MeshDFM([_res("wall", FAIL, 0.6, 0.8)])) == (None, "")


def test_family_relax_hook_drops_optional_stones():
    from karigar.packs.jewellery import families
    fam = families.get("ring_floral_cluster")
    spec = DesignSpec(name="f", piece_type="ring", family="ring_floral_cluster",
                      **fam.variant_fields("balanced"))
    out, what = meshdfm.relax(spec, MeshDFM([_res("setting", FAIL, 0.6, 0.8)]))
    assert out.params["petal_stones"] == 5 and "petal stones 6 -> 5" in what
    halo = families.get("ring_halo_solitaire")
    spec = DesignSpec(name="h", piece_type="ring", family="ring_halo_solitaire",
                      **halo.variant_fields("balanced"))
    out, what = meshdfm.relax(spec, MeshDFM([_res("setting", FAIL, 0.6, 0.8)]))
    assert out.params["shoulder_stones"] == 0


# ------------------------------------------------------------------ the one retry (solve)
class _Calls:
    def __init__(self, reports):
        self.reports, self.specs = list(reports), []

    def check(self, spec, scale, cfg=None):
        self.specs.append(spec)
        return self.reports.pop(0)


def _fake_core(self, spec, plan, on_iter=None):
    return Solved(spec, True, 1.1, plan.target_value, plan.target_value, 4, issues=["spec ok"])


def test_failed_check_retries_once_relaxed_then_passes(monkeypatch):
    bad = MeshDFM([_res("ring_shank", FAIL, 1.38, 1.5)])
    good = MeshDFM([_res("ring_shank", PASS, 1.62, 1.5), _res("wall", WARN, 0.85, 0.8, "top")])
    calls = _Calls([bad, good])
    monkeypatch.setattr(JewelleryPack, "_solve_core", _fake_core)
    monkeypatch.setattr(meshdfm, "check_spec", calls.check)
    s = PACK.solve(RING, PLAN)
    assert s.ok
    assert len(calls.specs) == 2 and calls.specs[1].width_mm < RING.width_mm   # relaxed spec
    assert any("retried once" in w and "ring_shank at 6 o'clock" in w for w in s.warnings)
    assert any(w.startswith("wall at top") for w in s.warnings)                # the warn
    assert [m["status"] for m in s.mesh_checks] == [PASS, WARN]
    assert any(i.startswith("mesh: ring_shank") for i in s.issues)


def test_failed_check_twice_reports_the_failing_rule(monkeypatch):
    bad = MeshDFM([_res("ring_shank", FAIL, 1.38, 1.5)])
    calls = _Calls([bad, MeshDFM([_res("ring_shank", FAIL, 1.45, 1.5)])])
    monkeypatch.setattr(JewelleryPack, "_solve_core", _fake_core)
    monkeypatch.setattr(meshdfm, "check_spec", calls.check)
    s = PACK.solve(RING, PLAN)
    assert not s.ok and len(calls.specs) == 2
    assert s.binding_constraint.startswith("mesh check: ring_shank at 6 o'clock")
    assert "1.45 mm < 1.5 mm" in s.explanation and "Retried once" in s.explanation
    assert len(s.alternatives) >= 2 and s.best_achievable["unit"] == "g"
    assert s.mesh_checks[0]["status"] == FAIL


def test_failed_build_retries_once_relaxed(monkeypatch):
    seen = []

    def core(self, spec, plan, on_iter=None):
        seen.append(spec)
        if len(seen) == 1:
            raise RuntimeError("boolean union produced no solid")
        return _fake_core(self, spec, plan)
    monkeypatch.setattr(JewelleryPack, "_solve_core", core)
    monkeypatch.setattr(meshdfm, "check_spec", lambda spec, s, cfg=None: MeshDFM([_res("wall", PASS, 1.2, 0.8)]))
    s = PACK.solve(RING, PLAN)
    assert s.ok and len(seen) == 2
    assert any("build failed" in w and "retried once" in w for w in s.warnings)


def test_failed_build_twice_names_the_build_rule(monkeypatch):
    def core(self, spec, plan, on_iter=None):
        raise RuntimeError("boolean union produced no solid")
    monkeypatch.setattr(JewelleryPack, "_solve_core", core)
    s = PACK.solve(RING, PLAN)
    assert not s.ok and s.binding_constraint.startswith("mesh check: build failed")


def test_infeasible_solve_is_not_mesh_checked(monkeypatch):
    def core(self, spec, plan, on_iter=None):
        return Solved(spec, False, 0.8, 1.0, 4.0, 3, binding_constraint="minimum ring shank thickness 1.5 mm")
    monkeypatch.setattr(JewelleryPack, "_solve_core", core)
    monkeypatch.setattr(meshdfm, "check_spec", lambda *a, **k: pytest.fail("checked an infeasible solve"))
    assert PACK.solve(RING, PLAN).binding_constraint == "minimum ring shank thickness 1.5 mm"


# ------------------------------------------------------------------ job card
def _plan():
    return Plan(True, target_value=4.0, detail={"casting_loss_pct": 3.0,
                                                "tolerance": {"pct": 4.0, "source": "default"}})


def test_mesh_results_go_into_the_job_card():
    rep = MeshDFM([_res("ring_shank", PASS, 1.7, 1.5), _res("wall", WARN, 0.83, 0.8, "top centre")])
    solved = with_mesh(Solved(RING, True, 1.0, 4.0, 4.0, 3, issues=["thickness 1.80 mm ≥ 1.5 mm"]), rep)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=4.0)
    from karigar.packs.jewellery import pricing
    job = job_card(RING, solved, brief, _plan(), {"width_mm": 3.0}, 1, pricing.rate_card())
    assert job["mesh_checks"] == rep.as_list()
    assert any(w.startswith("wall at top centre") for w in job["warnings"])
    assert "mesh: ring_shank at 6 o'clock: 1.7 mm ≥ 1.5 mm" in job["checks_passed"]
    for m in job["mesh_checks"]:
        assert m["status"] in (PASS, WARN, FAIL) and m["location"]
    from pathlib import Path
    md = job_card_md(job, {}, Path("."))
    assert "## Manufacturability (measured on the mesh)" in md
    assert "- PASS ring_shank at 6 o'clock" in md and "- WARN wall at top centre" in md
