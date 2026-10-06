from src.evaluation.judge import _parse_judgment, judge_synthesized_answer, resolve_judge_target


def test_parse_judgment_extracts_json_block():
    raw = 'Sure.\n{"score": 5, "faithfulness": 5, "coverage": 4, "verdict": "supported", "rationale": "Matches gold."}\n'
    parsed = _parse_judgment(raw)
    assert parsed == {
        "score": 5,
        "faithfulness": 5,
        "coverage": 4,
        "verdict": "supported",
        "rationale": "Matches gold.",
    }


def test_judge_uses_another_scayle_model(monkeypatch):
    monkeypatch.setenv("JUDGE_DISABLED", "false")
    monkeypatch.delenv("JUDGE_LLM_MODEL", raising=False)
    monkeypatch.setattr("src.evaluation.judge.pipeline_lm_identity", lambda: ("scayle", "qwen3"))
    monkeypatch.setattr("src.evaluation.judge.credentials_present_for", lambda provider: provider == "scayle")
    seen: dict[str, str] = {}

    def fake_chat(messages, *, provider, model):
        seen["provider"] = provider
        seen["model"] = model
        return '{"score": 4, "faithfulness": 4, "coverage": 3, "verdict": "partial", "rationale": "Some gold facts missing."}'

    monkeypatch.setattr("src.evaluation.judge.chat_completion", fake_chat)
    result = judge_synthesized_answer("How is marriage defined?", "gold text", "system text")
    assert result["available"] is True
    assert seen == {"provider": "scayle", "model": "glm-5.3-flash"}
    assert result["judge_lm"] == "scayle:glm-5.3-flash"
    assert result["pipeline_lm"] == "scayle:qwen3"
    assert result["score"] == 4
    assert result["verdict"] == "partial"


def test_judge_switches_off_qwen_when_pipeline_is_llama(monkeypatch):
    monkeypatch.setenv("JUDGE_DISABLED", "false")
    monkeypatch.setenv("JUDGE_LLM_MODEL", "glm-5.3-flash")
    monkeypatch.setattr("src.evaluation.judge.pipeline_lm_identity", lambda: ("scayle", "glm-5.3-flash"))
    monkeypatch.setattr("src.evaluation.judge.credentials_present_for", lambda provider: provider == "scayle")
    assert resolve_judge_target() == ("scayle", "kimi-k2.6")


def test_judge_needs_scayle_credentials(monkeypatch):
    monkeypatch.setenv("JUDGE_DISABLED", "false")
    monkeypatch.setattr("src.evaluation.judge.pipeline_lm_identity", lambda: ("scayle", "qwen3"))
    monkeypatch.setattr("src.evaluation.judge.credentials_present_for", lambda provider: False)
    assert resolve_judge_target() is None
    result = judge_synthesized_answer("q", "gold", "ans")
    assert result["available"] is False
    assert "Scayle" in result["reason"]
