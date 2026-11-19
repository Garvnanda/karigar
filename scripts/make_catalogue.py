"""Write console/catalogue.json: the 19 families with lighter/balanced/statement weights (Phase 10).

Run in WSL from the repo root (needs bpy): ./venv/bin/python scripts/make_catalogue.py
Weights are measured on the mesh (geometry.gold_volume × density), 22K unless the family says otherwise.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karigar.core import gold as G  # noqa: E402
from karigar.packs.jewellery import geometry, render  # noqa: E402
from karigar.packs.jewellery.designer import LABELS  # noqa: E402
from karigar.packs.jewellery.families import CATALOGUE, FAMILIES  # noqa: E402
from karigar.packs.jewellery.schema import DesignSpec  # noqa: E402


def main() -> None:
    out = []
    for name in CATALOGUE:
        f = FAMILIES[name]
        spec = DesignSpec(**{**f.default_spec, "piece_type": f.piece_type, "family": name, "name": f.title or name})
        row = {"family": name, "title": f.title or name, "piece_type": f.piece_type, "karat": spec.karat}
        try:
            weights = {}
            for lab in LABELS:
                v = DesignSpec(**{**f.variant_fields(lab), "piece_type": f.piece_type, "family": name,
                                  "name": f.title or name})
                weights[lab] = round(G.mm3_to_grams(geometry.gold_volume(v, 1.0), v.karat), 2)
            row["weights_g"] = weights
        except Exception as e:   # one family failing must not hide the rest
            row["error"] = f"{type(e).__name__}: {e}"[:200]
        row["default_g"] = round(G.mm3_to_grams(geometry.gold_volume(spec, 1.0), spec.karat), 2)
        if "--pictures" in sys.argv:   # studio/assets/<family>.png + .glb (draft render, ~3 s each)
            geometry.clear_scene()
            b = geometry.build(spec, 1.0)
            c, S = render.stage(b.gold, b.gems, spec.metal, spec.karat, spec.gem,
                                float_up=spec.piece_type == "pendant")
            assets = ROOT / "studio" / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            render.dress_pair([b.gold, *b.gems], b.mirror)
            render.export_glb([b.gold, *b.gems, *b.mirror], assets / f"{name}.glb")
            shots = render.render_views(c, S, assets / "_tmp", "draft")
            Path(shots["render_hero"]).replace(assets / f"{name}.png")
            row["picture"], row["model"] = f"assets/{name}.png", f"assets/{name}.glb"
        out.append(row)
        geometry.clear_scene()
    for p in (ROOT / "console" / "catalogue.json", ROOT / "studio" / "catalogue.json"):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"families": out}, indent=1))
        print(f"wrote {p} ({len(out)} families)")


if __name__ == "__main__":
    main()
