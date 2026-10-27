import json

import pytest

from backend import narrative
from backend.ingest import parse_session
from backend.narrative import Debrief, TyreNote, build_facts, check_faithfulness, generate_debrief, template_debrief
from backend.pipeline import load_config
from backend.rules import pick_takeaway, run_rules
from backend.stats import compute_stats

from .synth import CORNERS, make_csv

CFG = load_config()


@pytest.fixture(scope="module")
def analysed():
    st = compute_stats(parse_session(make_csv(profiles={c: [45] * 8 for c in CORNERS}).encode(), "t.csv"), CFG)
    flags = run_rules(st, CFG, {})
    return st, flags, pick_takeaway(flags)


def fake(takeaway_id, text="Your tyres averaged 45.0 °C."):
    return Debrief(headline="Cold tyres", summary=text, takeaway="Build heat on the out-lap.",
                   tyre_notes=[TyreNote(tyre=c, note="Cold.") for c in CORNERS],
                   takeaway_flag_id=takeaway_id, cited_flag_ids=[takeaway_id])


def test_template_passes_its_own_faithfulness_check(analysed):
    st, flags, tk = analysed
    d = template_debrief(st, flags, tk)
    assert check_faithfulness(d, build_facts(st, flags, tk, {})) == []
    assert d.takeaway == tk["action"]


def test_invented_number_is_caught(analysed):
    st, flags, tk = analysed
    issues = check_faithfulness(fake(tk["id"], "Lower pressure to 27.5 psi."), build_facts(st, flags, tk, {}))
    assert any("27.5" in i for i in issues)


def test_wrong_takeaway_is_caught(analysed):
    st, flags, tk = analysed
    issues = check_faithfulness(fake("F99"), build_facts(st, flags, tk, {}))
    assert any("Takeaway" in i for i in issues)


def test_supported_narrative_passes(analysed):
    st, flags, tk = analysed
    assert check_faithfulness(fake(tk["id"]), build_facts(st, flags, tk, {})) == []


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.delenv("DEBRIEF_DISABLE_LLM", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("GEMINI_MODEL", "g-lite,g-backup")
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    replies = {"gemini": [], "openrouter": []}
    calls = []

    def scripted(name):
        def call(system, user, schema, model, timeout=20):
            calls.append((name, model))
            r = replies[name].pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return call
    for name in replies:
        key, model, _ = narrative.PROVIDERS[name]
        monkeypatch.setitem(narrative.PROVIDERS, name, (key, model, scripted(name)))
    replies["calls"] = calls
    return replies


def test_unfaithful_draft_is_retried_then_accepted(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"] += [fake(tk["id"], "Set 19.9 psi."), fake(tk["id"])]
    out = generate_debrief(st, flags, tk, {})
    assert out["source"] == "llm" and out["provider"] == "gemini"
    assert out["attempts"][0]["issues"] and out["attempts"][1]["issues"] == []


def test_overloaded_model_falls_through_to_next_model(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"] += [narrative.ModelUnavailable("Model overloaded (503)."), fake(tk["id"])]
    out = generate_debrief(st, flags, tk, {})
    assert out["source"] == "llm" and out["model"] == "g-backup"
    assert providers["calls"] == [("gemini", "g-lite"), ("gemini", "g-backup")]


def test_gemini_error_falls_through_to_openrouter(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"] += [narrative.ModelUnavailable("Rate limit or free quota reached."),
                            narrative.ProviderError("The API key was rejected.")]
    providers["openrouter"].append(fake(tk["id"]))
    out = generate_debrief(st, flags, tk, {})
    assert out["provider"] == "openrouter"
    assert "quota" in out["attempts"][0]["error"]


def test_all_providers_failing_gives_template(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"] += [fake(tk["id"], "Set 19.9 psi."), fake(tk["id"], "Set 18.1 psi."),
                            narrative.ProviderError("network down")]
    providers["openrouter"].append(narrative.ProviderError("network down"))
    out = generate_debrief(st, flags, tk, {})
    assert out["source"] == "template" and out["takeaway"] == tk["action"]
    assert len(out["attempts"]) == 4


def test_time_budget_stops_slow_providers(analysed, providers, monkeypatch):
    st, flags, tk = analysed
    monkeypatch.setattr(narrative, "BUDGET_S", 0)
    out = generate_debrief(st, flags, tk, {})
    assert out["source"] == "template" and providers["calls"] == []
    assert "budget" in out["attempts"][0]["error"]


def test_ranges_and_decimal_percentages_are_not_flagged(analysed):
    st, flags, tk = analysed
    share = st["tyres"]["LF"]["share_in_window"]
    text = f"Your tyres sat outside the 60-90 °C window and the 60–90 °C band, in it {round(share * 100, 1)}% of the time."
    assert check_faithfulness(fake(tk["id"], text), build_facts(st, flags, tk, {})) == []


def test_no_keys_means_template(analysed, monkeypatch):
    st, flags, tk = analysed
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = generate_debrief(st, flags, tk, {})
    assert out["source"] == "template" and out["attempts"] == []


def _fake_post(payload, status=200):
    class R:
        status_code = status
        text = json.dumps(payload)

        def json(self):
            return payload
    return lambda url, headers, json, timeout: R()


def test_gemini_response_is_parsed(analysed, monkeypatch):
    st, flags, tk = analysed
    body = fake(tk["id"]).model_dump_json()
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(narrative.httpx, "post", _fake_post(
        {"candidates": [{"content": {"parts": [{"text": "```json\n" + body + "\n```"}]}}]}))
    assert narrative.call_gemini("sys", "user", narrative.Debrief, "gemini-flash-lite-latest").headline == "Cold tyres"


def test_openrouter_response_is_parsed(analysed, monkeypatch):
    st, flags, tk = analysed
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(narrative.httpx, "post", _fake_post(
        {"choices": [{"message": {"content": fake(tk["id"]).model_dump_json()}}]}))
    assert narrative.call_openrouter("sys", "user", narrative.Debrief, "openrouter/free").takeaway_flag_id == tk["id"]


def test_bad_key_is_reported(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad")
    monkeypatch.setattr(narrative.httpx, "post", _fake_post({"error": "no"}, status=403))
    with pytest.raises(narrative.ProviderError, match="key was rejected"):
        narrative.call_gemini("sys", "user", narrative.Debrief, "gemini-flash-lite-latest")


def test_overloaded_model_raises_model_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(narrative.httpx, "post", _fake_post({"error": "busy"}, status=503))
    with pytest.raises(narrative.ModelUnavailable):
        narrative.call_gemini("sys", "user", narrative.Debrief, "gemini-flash-latest")


def test_llm_never_sees_raw_telemetry(analysed):
    st, flags, tk = analysed
    facts = build_facts(st, flags, tk, {})
    assert "laps" in facts and "profile_straight" not in str(facts)


def test_no_takeaway_session_accepts_null_takeaway():
    st = compute_stats(parse_session(make_csv(profiles={c: [84, 81, 78, 75, 72, 69, 66, 63] for c in CORNERS},
                                              corner_profiles={c: [72] * 8 for c in CORNERS}, pressure_psi=32).encode(), "ok.csv"), CFG)
    flags = run_rules(st, CFG, {})
    assert pick_takeaway(flags) is None
    facts = build_facts(st, flags, None, {})
    d = Debrief(headline="All good", summary="Nothing to change.", takeaway="Keep the current setup.",
                tyre_notes=[TyreNote(tyre=c, note="Fine.") for c in CORNERS], takeaway_flag_id=None, cited_flag_ids=[])
    assert check_faithfulness(d, facts) == []
    assert check_faithfulness(template_debrief(st, flags, None), facts) == []


def test_garbled_characters_are_rejected(analysed):
    st, flags, tk = analysed
    issues = check_faithfulness(fake(tk["id"], "Averaged 45.0 ÞgC."), build_facts(st, flags, tk, {}))
    assert any("Unexpected characters" in i for i in issues)


def test_unsupported_causal_claim_is_rejected(analysed):
    st, flags, tk = analysed
    facts = build_facts(st, flags, tk, {})
    issues = check_faithfulness(fake(tk["id"], "Your tyres were cold due to the weather."), facts)
    assert any("due to" in i for i in issues)
    assert check_faithfulness(fake(tk["id"], "Cold weather makes heat harder to build."), facts) == []


def _report(st, flags, tk):
    return {"stats": st, "flags": flags, "takeaway_flag_id": tk["id"], "context": {}, "setup_sheet": {"corners": {}}}


def test_question_answered_from_facts(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"].append(narrative.Answer(answer="Your tyres averaged 45.0 °C, below the window.", cited_flag_ids=[tk["id"]]))
    out = narrative.answer_question(_report(st, flags, tk), "Why are my tyres cold?")
    assert out["source"] == "llm" and "45.0" in out["answer"]


def test_question_answer_with_invented_number_is_rejected(analysed, providers):
    st, flags, tk = analysed
    providers["gemini"] += [narrative.Answer(answer="Set 27.3 psi.")] * 4
    providers["openrouter"].append(narrative.ProviderError("down"))
    out = narrative.answer_question(_report(st, flags, tk), "What pressure?")
    assert out["source"] == "none" and out["answerable"] is False


def test_numbers_from_the_question_are_allowed(analysed):
    st, flags, tk = analysed
    report = _report(st, flags, tk)
    facts = narrative.qa_facts(report)
    ans = narrative.Answer(answer="Running 27.5 psi isn't something this session tested.", answerable=False)
    assert narrative.check_answer(ans, facts, "Should I run 27.5 psi?") == []


def test_questions_need_a_provider(analysed, monkeypatch):
    st, flags, tk = analysed
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert narrative.answer_question(_report(st, flags, tk), "Why?")["answerable"] is False


def test_hedged_cause_allowed_definite_cause_rejected(analysed):
    st, flags, tk = analysed
    facts = build_facts(st, flags, tk, {})
    assert check_faithfulness(fake(tk["id"], "Your tyres were likely cold because the air was cool."), facts) == []
    issues = check_faithfulness(fake(tk["id"], "Your tyres were cold largely because the air was cool."), facts)
    assert any("definite cause" in i for i in issues)
