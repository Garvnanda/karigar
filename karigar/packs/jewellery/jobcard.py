"""Job card for the workshop, as Markdown (Phase 5, spec §10 Production package).

Pure Python (no bpy) so it is testable on its own. `JewelleryPack.deliver` builds the `job`
dict (also written as job_card.json) and calls `job_card_md`. Every number comes from code:
the solver, the mesh dimensions, the brief and the rate card.
"""
from __future__ import annotations

from pathlib import Path

from karigar.core import gold as G

FINISHING = {
    "yellow": "High polish; ultrasonic clean; steam.",
    "rose": "High polish; ultrasonic clean; steam. Keep rose alloy away from rhodium baths.",
    "white": "High polish, then rhodium plate; ultrasonic clean; steam.",
}
PIECE_FINISHING = {
    "ring": "Round the inner band (comfort edge); check the finger hole against the size after polishing.",
    "bangle": "Round the inner edge; check the inner diameter against the size after polishing.",
    "pendant": "Clean the bail hole; check a chain passes freely.",
    "chain": "Check every link moves freely; solder and test the clasp.",
    "coin": "Keep the stamp crisp; do not over-polish the face.",
    "earring": "Fit and test posts/backs on both earrings; match the pair by weight.",
    "nosepin": "Smooth the pin tip; fit the screw/back.",
}
HUID = ("HUID reminder: send the finished piece for BIS hallmarking before sale; every gold article "
        "must carry its 6-digit HUID ({n} × ₹{fee}). Record the HUID on this card.")


def size_text(piece: str, brief) -> str:
    if piece == "ring":
        s = f"Indian size {brief.ring_size}, " if brief.ring_size else ""
        return f"{s}inner diameter {brief.ring_inner_d_mm:g} mm"
    if piece == "bangle":
        return f"inner diameter {brief.bangle_inner_d_mm:g} mm"
    if piece == "chain" and brief.length_in:
        return f"length {brief.length_in} in"
    return "not applicable"


def _rel(path, base: Path) -> str:
    p = Path(path)
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.name


def job_card_md(job: dict, renders: dict, base: Path) -> str:
    """Markdown job card: renders, dimensions, size, purity, weights, stones, finishing,
    HUID reminder and rule warnings."""
    k = job["karat"]
    out = [f"# Job card — {job['design']}", ""]
    out += [f"- Piece: {job['piece']}" + (f" (family {job['family']})" if job.get("family") else ""),
            f"- Pieces to cast: {job['pieces_to_cast']}", ""]
    out += ["## Renders", ""]
    out += [f"![{name}]({_rel(p, base)})" for name, p in sorted(renders.items())] or ["(none)"]
    out += ["", "## Dimensions", ""]
    out += [f"- {key.replace('_', ' ')}: {val}" for key, val in job["dimensions_mm"].items()] or ["(none)"]
    out += ["", "## Size", "", f"- {job['size']}", ""]
    out += ["## Purity", "", f"- {k}K {job['metal']} gold, fineness {G.purity(k) * 1000:.0f}", ""]
    out += ["## Weights", "",
            f"- Modelled (wax/CAD): {job['modelled_weight_g']} g = casting weight, stone seats cut",
            f"- Expected finished: {job['expected_finished_weight_g']} g"
            + (f" ± {job['tolerance_g']:.2f} g" if job.get("tolerance_g") is not None else "")
            + f" (casting + finishing loss {job['assumed_casting_loss_pct']}%"
            + (f" = {job['expected_loss_g']:.2f} g" if job.get("expected_loss_g") is not None else "") + ")",
            *([f"- Tolerance: ±{job['tolerance_pct']:g}% — {job['tolerance_source']}"]
              if job.get("tolerance_source") else []),
            f"- STL scaled up {job['stl_shrinkage_pct']:g}% for casting shrinkage; weights above are "
            "for the unscaled design",
            f"- {job['tolerance_note']}", ""]
    out += ["## Stones", ""]
    st = job.get("stone")
    if st:
        line = f"- {st['type']}: {st['diameter_mm']} mm, about {st['approx_ct']} ct, {st['setting']} setting"
        if st.get("size_assumed"):
            line += " — stone size assumed (the design's own stone; the customer named no size)"
        out.append(line)
    else:
        out.append("- none")
    out += ["", "## Finishing notes", "", f"- {FINISHING.get(job['metal'], FINISHING['yellow'])}"]
    if job["piece"] in PIECE_FINISHING:
        out.append(f"- {PIECE_FINISHING[job['piece']]}")
    out.append("")
    out += ["## Hallmarking", "", f"- {HUID.format(n=job['hallmark_articles'], fee=job['hallmark_fee_inr'])}",
            "- HUID: ______", ""]
    out += ["## Rule warnings", ""]
    out += [f"- ⚠ {w}" for w in job.get("warnings", [])] or ["- none"]
    out += ["", "## Manufacturability (measured on the mesh)", ""]
    mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    out += [f"- {mark.get(m['status'], m['status'].upper())} {m['text']}"
            for m in job.get("mesh_checks", [])] or ["- not checked"]
    out += ["", "## Checks passed", ""]
    out += [f"- {c}" for c in job.get("checks_passed", [])] or ["- none recorded"]
    return "\n".join(out) + "\n"
