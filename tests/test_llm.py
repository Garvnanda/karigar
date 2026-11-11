import json
import subprocess

import pytest

from karigar.core import llm

KEY = "sk-test-abcdefghijklmnopqrstuvwxyz0123456789"


class FakeRun:
    """Stands in for subprocess.run; records the call."""

    def __init__(self, stdout="", stderr="", rc=0, exc=None):
        self.stdout, self.stderr, self.rc, self.exc = stdout, stderr, rc, exc
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(cmd, self.rc, self.stdout, self.stderr)


@pytest.fixture
def agentrouter(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "none.env")
    monkeypatch.setenv("KARIGAR_LLM_BACKEND", "agentrouter")
    monkeypatch.setenv("AGENTROUTER_API_KEY", KEY)
    monkeypatch.setenv("KARIGAR_MODEL", "gpt-6.1-sol")


def ok_stdout(result):
    return "noise line\n" + json.dumps({"is_error": False, "result": result})


def test_backend_none_returns_none_without_calling(monkeypatch):
    run = FakeRun()
    assert llm.complete_json("sys", "hi", runner=run) is None
    assert run.calls == []


def test_auto_picks_agentrouter_when_key_set(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "none.env")
    monkeypatch.setenv("KARIGAR_LLM_BACKEND", "auto")
    monkeypatch.setenv("AGENTROUTER_API_KEY", KEY)
    assert llm.backend() == "agentrouter"
    monkeypatch.delenv("AGENTROUTER_API_KEY")
    assert llm.backend() == "none"


def test_agentrouter_call_shape_and_key_kept_out_of_argv(agentrouter):
    run = FakeRun(stdout=ok_stdout('{"piece_type": "ring"}'))
    out = llm.complete_json("You are Sakhi.", "ek ring", runner=run)
    assert out == {"piece_type": "ring"}
    cmd, kw = run.calls[0]
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "gpt-6.1-sol"
    assert "--append-system-prompt" in cmd and "--system-prompt" not in cmd
    assert kw["input"] == "ek ring"
    assert kw["env"]["ANTHROPIC_BASE_URL"] == "https://agentrouter.org"
    assert kw["env"]["ANTHROPIC_AUTH_TOKEN"] == KEY
    assert kw["env"]["ANTHROPIC_API_KEY"] == ""
    assert not any(KEY in part for part in cmd)
    assert kw["timeout"] == llm.DEFAULT_TIMEOUT_S


def test_json_inside_prose_or_fences_is_extracted(agentrouter):
    run = FakeRun(stdout=ok_stdout('Sure:\n```json\n[{"name": "A"}]\n```'))
    assert llm.complete_json("s", "u", runner=run) == [{"name": "A"}]


@pytest.mark.parametrize("run", [
    FakeRun(exc=subprocess.TimeoutExpired("claude", 45)),
    FakeRun(exc=FileNotFoundError("claude")),
    FakeRun(stdout="not json at all", rc=1),
    FakeRun(stdout=json.dumps({"is_error": True, "result": "API Error: 503 overloaded"})),
    FakeRun(stdout=ok_stdout("no json here")),
], ids=["timeout", "no-cli", "unparseable", "provider-error", "reply-without-json"])
def test_every_failure_returns_none_so_caller_falls_back(agentrouter, run):
    assert llm.complete_json("s", "u", runner=run) is None


def test_error_output_never_leaks_key(agentrouter, capsys):
    run = FakeRun(stdout=f"boom {KEY} and fragment {KEY[3:20]}", rc=1)
    assert llm.complete_json("s", "u", runner=run) is None
    err = capsys.readouterr().err
    assert KEY not in err and KEY[3:20] not in err


def test_tests_never_see_the_real_env_file():
    assert llm.ENV_FILE.name == "no.env" and not llm.ENV_FILE.exists()
    llm.load_env_file()
    import os
    assert "AGENTROUTER_API_KEY" not in os.environ


def test_redact_removes_key_fragments_and_sk_tokens():
    s = llm.redact(f"a {KEY} b {KEY[5:30]} c sk-otherkey12345", KEY)
    assert KEY not in s and KEY[5:30] not in s and "sk-otherkey12345" not in s


def test_env_file_loaded_without_overriding(monkeypatch, tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nKARIGAR_TEST_A=from_file\nKARIGAR_TEST_B='quoted'\n", encoding="utf-8")
    monkeypatch.setenv("KARIGAR_TEST_A", "from_env")
    monkeypatch.delenv("KARIGAR_TEST_B", raising=False)
    llm.load_env_file(f)
    import os
    assert os.environ["KARIGAR_TEST_A"] == "from_env"
    assert os.environ["KARIGAR_TEST_B"] == "quoted"
    monkeypatch.delenv("KARIGAR_TEST_B")


def test_brief_falls_back_to_regex_when_llm_fails(agentrouter, monkeypatch):
    from karigar.packs.jewellery import brief as B
    run = FakeRun(exc=subprocess.TimeoutExpired("claude", 45))
    monkeypatch.setattr(llm.subprocess, "run", run)
    b, q = B.parse("purani 22K chain 6.2g se 22K ruby lotus pendant banao")
    assert len(run.calls) == 1  # the patched runner was used, not the real CLI
    assert q is None and b.piece_type == "pendant" and b.old_gold.weight_g == 6.2
