from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .rules import NAMES

log = logging.getLogger(__name__)

BUDGET_S = float(os.environ.get("DEBRIEF_LLM_BUDGET_S", 40))
QA_BUDGET_S = float(os.environ.get("DEBRIEF_QA_BUDGET_S", 20))

SYSTEM_PROMPT = """You write post-session tyre debriefs for club-level racers who are not data engineers.

You receive FACTS: verified statistics and rule-engine flags computed from Team Plus Wheel Turtle tyre-temperature data. Your job is to explain them, not to analyse the data yourself.

Rules:
- Use only the facts provided. Do not introduce any diagnosis, cause, number or recommendation that is not in a flag.
- Only state a cause when a flag's detail states it, and keep the flag's hedging ("a sign of", "makes it harder", "usually goes with"). If you link a cause that a flag only hints at, hedge it ("likely because", "partly due to"); never state it as certain.
- Every number you write must appear in the facts, written the same way (you may round a percentage share such as 0.183 to 18%).
- Explain any technical term in a few plain words the first time you use it (for example, camber is the inward tilt of the wheel).
- The takeaway must restate the action of the flag given as takeaway_flag_id, and nothing else.
  If takeaway_flag_id is null, nothing needs changing: set takeaway_flag_id to null and make the takeaway a short, number-free note to keep the current setup.
- Write in second person, calm and practical. No hype, no hedging boilerplate.
- headline: one sentence, at most 15 words.
- summary: 3-5 sentences covering the most important flags in priority order.
- tyre_notes: one or two sentences per tyre (LF, RF, LR, RR).
- cited_flag_ids: the ids of every flag you relied on. Never put flag ids such as "F1" in the prose.

Reply with a single JSON object and nothing else, matching this shape:
{"headline": str, "summary": str, "tyre_notes": [{"tyre": "LF"|"RF"|"LR"|"RR", "note": str}, ...4 items],
 "takeaway": str, "takeaway_flag_id": str, "cited_flag_ids": [str, ...]}"""


QA_PROMPT = """You answer a racer's questions about one track session. You receive FACTS: verified statistics, rule-engine findings (flags), a setup sheet for the next session and driver-style metrics, computed from Team Plus Wheel Turtle data, plus the QUESTION.

Rules:
- Answer only from the facts. If the facts cannot answer the question, set answerable to false and say in one sentence what this session's data can't tell.
- Recommend only actions that appear in a flag's action or in the setup sheet. You may explain tyre concepts in general terms (for example what camber is) without numbers.
- Every number you write must appear in the facts or the question, written the same way.
- Only state a cause when a flag's detail states it, keeping its hedging; if you link a cause, hedge it ("likely because").
- Plain words, second person, at most 120 words. Never put flag ids such as "F1" in the prose.

Reply with a single JSON object and nothing else: {"answer": str, "answerable": bool, "cited_flag_ids": [str, ...]}"""


class Answer(BaseModel):
    answer: str
    answerable: bool = True
    cited_flag_ids: list[str] = Field(default_factory=list)


class TyreNote(BaseModel):
    tyre: Literal["LF", "RF", "LR", "RR"]
    note: str


class Debrief(BaseModel):
    headline: str
    summary: str
    tyre_notes: list[TyreNote] = Field(min_length=4, max_length=4)
    takeaway: str
    takeaway_flag_id: str | None = None
    cited_flag_ids: list[str]


def build_facts(stats: dict, flags: list[dict], takeaway: dict | None, context: dict) -> dict:
    tyres = {}
    for c, t in stats["tyres"].items():
        tyres[c] = {
            "name": NAMES[c], "average_c": t["average_c"], "peak_c": t["peak_c"],
            # Pre-converted: given the raw 0.749 share, a live model wrote "749%".
            "in_window_pct": round(t["share_in_window"] * 100) if t["share_in_window"] is not None else None,
            "inside_middle_outside_c": [t["all"].get("inner"), t["all"].get("middle"), t["all"].get("outer")],
            "pressure_psi": t.get("pressure_psi"),
        }
    return {
        "session": stats["session"],
        "car": {k: v for k, v in context.items() if v not in (None, "")},
        "laps": {k: stats["lap_summary"][k] for k in ("valid", "best_lap", "best_time_s", "median_time_s", "std_time_s")},
        "tyres": tyres,
        "flags": [{k: f[k] for k in ("id", "rule", "severity", "title", "detail", "action", "evidence")} for f in flags],
        "takeaway_flag_id": takeaway["id"] if takeaway else None,
    }


_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_CAUSAL = ("due to", "caused by", "because", "the reason")
_HEDGES = {"likely", "probably", "partly", "possibly", "may", "might", "could", "can", "often", "usually", "tends"}
_ALLOWED_NON_ASCII = set("°–—‘’“”…−·×")
_RANGE = re.compile(r"(?<=\d)\s*[-–—]\s*(?=\d)")


def _numbers_in(obj) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found |= _numbers_in(v)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        found.add(float(obj))
        if 0 <= obj <= 1:
            pct = obj * 100
            found.update({round(pct), round(pct, 1), float(math.floor(pct)), float(math.ceil(pct))})
        found.add(float(round(obj)))
        if obj >= 60:
            m, s = divmod(obj, 60)
            found.update({float(int(m)), round(s, 3), float(int(s))})
    elif isinstance(obj, str):
        found |= {float(x) for x in _NUM.findall(_RANGE.sub(" ", obj))}
    return found


def _text_issues(text: str, facts: dict, extra_allowed: set[float] = frozenset()) -> list[str]:
    issues = []
    allowed = _numbers_in(facts) | {1.0, 2.0, 3.0, 4.0} | set(extra_allowed)
    for raw in _NUM.findall(_RANGE.sub(" ", text.replace("°", " "))):
        val = float(raw)
        if not any(abs(val - a) <= 0.051 for a in allowed):
            issues.append(f"Number {raw} in the narrative is not in the facts.")
    facts_text = json.dumps(facts, ensure_ascii=False).lower()
    for sentence in re.split(r"(?<=[.!?])\s+", text.lower()):
        for phrase in _CAUSAL:
            if phrase in sentence and phrase not in facts_text and not any(h in sentence.split() for h in _HEDGES):
                issues.append(f'The narrative states a definite cause with "{phrase}", which no flag states. '
                              'Hedge it ("likely because", "partly due to") or use the flag\'s own wording.')
    odd = sorted({ch for ch in text if ord(ch) > 127 and ch not in _ALLOWED_NON_ASCII})
    if odd:
        issues.append(f"Unexpected characters in the narrative: {''.join(odd)} (write the degree sign as °).")
    return issues


def check_faithfulness(debrief: Debrief, facts: dict) -> list[str]:
    text = " ".join([debrief.headline, debrief.summary, debrief.takeaway] + [n.note for n in debrief.tyre_notes])
    issues = _text_issues(text, facts)
    flag_ids = {f["id"] for f in facts["flags"]}
    if (debrief.takeaway_flag_id or None) != facts["takeaway_flag_id"]:
        issues.append(f"Takeaway cites {debrief.takeaway_flag_id}, expected {facts['takeaway_flag_id']}.")
    unknown = [i for i in debrief.cited_flag_ids if i not in flag_ids]
    if unknown:
        issues.append(f"Narrative cites unknown flags: {', '.join(unknown)}.")
    if sorted(n.tyre for n in debrief.tyre_notes) != sorted(NAMES):
        issues.append("Tyre notes do not cover all four tyres exactly once.")
    return issues


def template_debrief(stats: dict, flags: list[dict], takeaway: dict | None) -> Debrief:
    actionable = [f for f in flags if f["severity"] in ("high", "medium", "low")]
    headline = takeaway["title"] if takeaway else "No setup changes stand out from this session"
    if actionable:
        summary = " ".join(f"{f['title']}. {f['detail']}" for f in actionable[:3])
    else:
        summary = "Tyre temperatures, camber and pressure indicators were all inside the configured ranges."
    notes = []
    for c, t in stats["tyres"].items():
        tyre_flags = [f["title"].split(": ", 1)[-1] for f in actionable if c in f["tyres"]]
        base = (f"Averaged {t['average_c']} °C, peaking at {t['peak_c']} °C, and was in the working window "
                f"{round((t['share_in_window'] or 0) * 100)}% of the time.")
        notes.append(TyreNote(tyre=c, note=base + (f" Flagged: {'; '.join(tyre_flags)}." if tyre_flags else "")))
    return Debrief(
        headline=headline, summary=summary, tyre_notes=notes,
        takeaway=takeaway["action"] if takeaway else "Keep the current setup and focus on consistent laps.",
        takeaway_flag_id=takeaway["id"] if takeaway else None,
        cited_flag_ids=[f["id"] for f in actionable[:3]],
    )


class ProviderError(RuntimeError):
    pass


def check_answer(answer: Answer, facts: dict, question: str) -> list[str]:
    issues = _text_issues(answer.answer, facts, _numbers_in(question))
    flag_ids = {f["id"] for f in facts["flags"]}
    unknown = [i for i in answer.cited_flag_ids if i not in flag_ids]
    if unknown:
        issues.append(f"Answer cites unknown flags: {', '.join(unknown)}.")
    return issues


def _parse_json(text: str, schema=None):
    schema = schema or Debrief
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ProviderError("The model did not return JSON.")
    try:
        return schema.model_validate_json(text[start:end + 1])
    except ValidationError as exc:
        raise ProviderError(f"The model's JSON did not match the expected schema: {exc.errors()[:2]}") from exc


def _user_message(payload: str, feedback: list[str] | None) -> str:
    msg = payload
    if feedback:
        msg += ("\n\nYour previous draft was rejected by the fact check for these reasons. "
                "Fix them and reply with the corrected JSON only:\n- " + "\n- ".join(feedback))
    return msg


class ModelUnavailable(ProviderError):
    pass


def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Could not reach the API ({type(exc).__name__}).") from exc
    if r.status_code in (401, 403):
        raise ProviderError("The API key was rejected.")
    if r.status_code == 429:
        raise ModelUnavailable("Rate limit or free quota reached.")
    if r.status_code in (404, 503):
        raise ModelUnavailable("Model retired or not found." if r.status_code == 404 else "Model overloaded (503).")
    if r.status_code >= 400:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def call_gemini(system: str, user: str, schema, model: str, timeout: float = 20):
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
        },
        timeout,
    )
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        reason = (data.get("promptFeedback") or {}).get("blockReason") or data.get("candidates", [{}])[0].get("finishReason")
        raise ProviderError(f"Gemini returned no text ({reason}).") from exc
    return _parse_json("".join(p.get("text", "") for p in parts if not p.get("thought")), schema)


def call_openrouter(system: str, user: str, schema, model: str, timeout: float = 20):
    data = _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "X-Title": "Tyre Debrief Assistant"},
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        },
        timeout,
    )
    try:
        return _parse_json(data["choices"][0]["message"]["content"], schema)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"OpenRouter returned no message: {str(data)[:200]}") from exc


PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", ("GEMINI_MODEL", "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-flash-latest"), call_gemini),
    "openrouter": ("OPENROUTER_API_KEY", ("OPENROUTER_MODEL", "openrouter/free"), call_openrouter),
}


def configured_providers() -> list[str]:
    if os.environ.get("DEBRIEF_DISABLE_LLM") == "1":
        return []
    return [name for name, (key, _, _) in PROVIDERS.items() if os.environ.get(key)]


def llm_available() -> bool:
    return bool(configured_providers())


def _run(system: str, payload: str, schema, check, budget: float | None = None) -> tuple[object | None, list[dict], str | None, str | None]:
    attempts = []
    deadline = time.monotonic() + (BUDGET_S if budget is None else budget)
    for name in configured_providers():
        _, (model_env, model_default), call = PROVIDERS[name]
        models = [m.strip() for m in os.environ.get(model_env, model_default).split(",") if m.strip()]
        for model in models:
            feedback = None
            for attempt in (1, 2):
                remaining = deadline - time.monotonic()
                if remaining < 2:
                    attempts.append({"provider": name, "model": model, "attempt": attempt, "error": "Time budget used up."})
                    return None, attempts, None, None
                try:
                    candidate = call(system, _user_message(payload, feedback), schema, model, timeout=remaining)
                except ProviderError as exc:
                    attempts.append({"provider": name, "model": model, "attempt": attempt, "error": str(exc)})
                    log.warning("%s/%s failed: %s", name, model, exc)
                    break
                issues = check(candidate)
                attempts.append({"provider": name, "model": model, "attempt": attempt, "issues": issues})
                if not issues:
                    return candidate, attempts, name, model
                log.warning("%s/%s failed the fact check: %s", name, model, issues)
                feedback = issues
    return None, attempts, None, None


def generate_debrief(stats: dict, flags: list[dict], takeaway: dict | None, context: dict) -> dict:
    facts = build_facts(stats, flags, takeaway, context)
    payload = "FACTS:\n" + json.dumps(facts, ensure_ascii=False)
    candidate, attempts, name, model = _run(SYSTEM_PROMPT, payload, Debrief, lambda d: check_faithfulness(d, facts))
    if candidate is not None:
        return {**candidate.model_dump(), "source": "llm", "provider": name, "model": model, "attempts": attempts}
    return template_narrative(stats, flags, takeaway, attempts=attempts)


def template_narrative(stats: dict, flags: list[dict], takeaway: dict | None, pending: bool = False, attempts=None) -> dict:
    debrief = template_debrief(stats, flags, takeaway)
    return {**debrief.model_dump(), "source": "pending" if pending else "template", "provider": None, "model": None,
            "attempts": attempts or []}


def qa_facts(report: dict) -> dict:
    stats, flags = report["stats"], report["flags"]
    takeaway = next((f for f in flags if f["id"] == report.get("takeaway_flag_id")), None)
    facts = build_facts(stats, flags, takeaway, report.get("context") or {})
    for c, t in stats["tyres"].items():
        facts["tyres"][c]["by_driving_state"] = {
            v: {k: (t.get("views") or {}).get(v, {}).get(k) for k in ("average_c", "peak_c", "inner", "middle", "outer")}
            for v in ("straight", "corner")}
    facts["setup_sheet"] = report.get("setup_sheet")
    facts["driver_style"] = stats.get("driver_style")
    facts["laps_detail"] = [{k: l.get(k) for k in ("lap", "time_s", "flying", "tyre_avg_c", "full_throttle_pct", "coasting_pct")}
                            for l in stats["laps"] if l.get("valid")]
    return facts


def answer_question(report: dict, question: str) -> dict:
    if not configured_providers():
        return {"answer": "Questions need the AI to be switched on: add a Gemini or OpenRouter key to the .env file.",
                "answerable": False, "cited_flag_ids": [], "source": "none", "model": None}
    facts = qa_facts(report)
    payload = "FACTS:\n" + json.dumps(facts, ensure_ascii=False) + "\n\nQUESTION:\n" + question
    candidate, attempts, name, model = _run(QA_PROMPT, payload, Answer, lambda a: check_answer(a, facts, question),
                                            budget=QA_BUDGET_S)
    if candidate is None:
        return {"answer": "I couldn't give a checked answer to that from this session's data. Try asking about a specific "
                          "tyre, the pressures, camber or your best lap.",
                "answerable": False, "cited_flag_ids": [], "source": "none", "model": None, "attempts": attempts}
    return {**candidate.model_dump(), "source": "llm", "model": model, "attempts": attempts}
