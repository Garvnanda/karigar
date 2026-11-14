"""Phase 7 replies: every number shown comes from the order record (code), the wording around
it has none; files go out as links (Nonilion renders no images); the service side imports
nothing heavy (no bpy, pydantic, LLM) so it runs on Render with no dependencies."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from karigar.service import replies
from karigar.service.convo import ref_line
from service_fakes import QUOTES, WEIGHTS

ROOT = Path(__file__).resolve().parents[1]
NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def record_numbers(obj) -> list[float]:
    """Every numeric value in the record, plus numbers written inside its code-made strings."""
    out = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return [float(m.replace(",", "")) for m in NUM.findall(obj)]
    if isinstance(obj, dict):
        for v in obj.values():
            out += record_numbers(v)
    if isinstance(obj, list):
        for v in obj:
            out += record_numbers(v)
    return out


def reply_numbers(text: str) -> list[str]:
    text = re.sub(r"\]\([^)]*\)", "]", text)                 # link targets (tokens) are not numbers
    text = re.sub(r"ORD-[\w-]+|K-[0-9a-f]{16}", "", text)     # ids
    return NUM.findall(text)


def assert_numbers_from_record(text: str, record: dict) -> None:
    have = record_numbers(record)
    for tok in reply_numbers(text):
        v = float(tok.replace(",", ""))
        dec = len(tok.split(".")[1]) if "." in tok else 0
        assert any(round(x, dec) == v for x in have), f"{tok} in reply is not in the order record"


def results(files=True):
    out = []
    for i, n in enumerate(("Plain", "Floral", "Twist")):
        r = {"variant": n, "version": i + 1, "weights": WEIGHTS[i], "quote": QUOTES[i], "files": {}}
        if files:
            r["files"] = {"render_hero": f"/files/tok{i}/v{i + 1}-render_hero.png",
                          "stl": f"/files/tokS{i}/v{i + 1}-casting.stl",
                          "job_card_md": f"/files/tokJ{i}/v{i + 1}-job_card.md",
                          "quote": f"/files/tokQ{i}/v{i + 1}-quote.json"}
        out.append(r)
    return out


ORDER = {"status": "done", "order_id": "ORD-20261113-101500-a3f9", "lang": "en", "results": results()}
EDIT = {"status": "done", "order_id": "ORD-1", "lang": "en",
        "edit": {"summary": "v4 (from v2): size 9.9 mm → 10.89 mm. Weight 6.09 g → 6.10 g, price ₹72,345 → ₹72,511",
                 "to_version": 4},
        "results": [{"variant": "Floral", "version": 4, "files": {},
                     "weights": {"casting_g": 6.29, "finished_g": 6.101, "tolerance_g": 0.24},
                     "quote": {"total": 72511, "to_pay": 12011}}]}
INFEASIBLE = {"status": "infeasible", "order_id": "ORD-2", "lang": "en",
              "explanation": "too little gold: the lightest castable version finishes at 1.85 g; you have 1.16 g.",
              "infeasible": {"binding_constraint": "minimum ring shank thickness 1.5 mm",
                             "best_achievable": {"value": 1.85, "unit": "g"},
                             "alternatives": ["a 0.25 ct diamond at 1.85 g", "a slimmer design"]}}
NEEDS = {"status": "needs_info", "order_id": "ORD-3", "lang": "hinglish",
         "reply": "Ring ka size batayiye (jaise 12).", "question": "q"}


@pytest.mark.parametrize("record", [ORDER, EDIT, INFEASIBLE, NEEDS], ids=["order", "edit", "infeasible", "needs"])
@pytest.mark.parametrize("agent", ["karigar", "sakhi"])
def test_every_number_in_reply_is_in_the_record(record, agent):
    text = replies.render(record, "https://k.onrender.com", agent) + "\n\n" + ref_line("K-0123456789abcdef")
    assert reply_numbers(text), "the test needs numbers to check"
    assert_numbers_from_record(text, record)


def test_partial_reply_numbers_from_record_and_no_links():
    partial = dict(ORDER, results=results(files=False))
    text = replies.render(partial, "https://k", "karigar", files_pending=True, note="renders later")
    assert_numbers_from_record(text, partial)
    assert "](" not in text and "still being made" in text


def test_a_made_up_number_is_caught():
    with pytest.raises(AssertionError):
        assert_numbers_from_record("total ₹99,999", ORDER)


def test_files_are_https_links_not_images():
    text = replies.render(ORDER, "https://k.onrender.com", "karigar")
    assert "![" not in text
    assert "[photo](https://k.onrender.com/files/tok0/v1-render_hero.png)" in text
    assert "[STL](https://k.onrender.com/files/tokS0/v1-casting.stl)" in text


def test_shown_values_match_the_record_exactly():
    text = replies.render(ORDER, "", "karigar")
    assert "4.97 g ± 0.20 g finished (cast 5.12 g), total ₹61,234" in text
    assert "₹83,456" in text and replies.inr(12345678) == "₹1,23,45,678" and replies.inr(-500) == "-₹500"


def test_service_side_imports_no_bpy_pydantic_or_llm():
    code = ("import sys; import karigar.service.http, karigar.service.core, karigar.service.jobs; "
            "bad = [m for m in ('bpy', 'pydantic', 'anthropic', 'karigar.core.llm', "
            "'karigar.core.orchestrator', 'karigar.packs.jewellery') if m in sys.modules]; "
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_service_has_no_llm_or_subprocess_calls():
    src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "karigar" / "service").glob("*.py")
                  if p.name != "worker.py")
    assert "complete_json" not in src and "subprocess" not in src and "Orchestrator(" not in src
