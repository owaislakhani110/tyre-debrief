# Tyre Debrief Assistant

AI-assisted tyre-temperature debriefs for Team Plus Wheel Turtle sensors.
ITS Capstone 9785, project 2026-S2-06.

Upload a session (the AiM logger's .xrk file or a CSV export) and get one priority action, a "before your next
session" setup sheet (pressure, camber, heat shape, tools), a plain-English debrief you can ask questions about,
a tyre-by-tyre view of temperature across the tread, driver-style notes, and lap-by-lap trends. Every finding
traces back to a rule and a number.

```
CSV ──► ingest.py ──► stats.py ──► rules.py ──► narrative.py ──► report (SQLite + web UI)
        parse &       clean, per-   thresholds   LLM rewords   
        validate      tyre/lap      from YAML    verified flags,
                      statistics                 fact-checked
```

## Run it

New Mac? Follow **[SETUP.md](SETUP.md)** for step-by-step instructions.

Already set up:

```bash
source .venv/bin/activate
python -m uvicorn backend.main:app
# open http://localhost:8000
```

Tests: `.venv/bin/python -m pytest`

Batch-analyse sessions: `.venv/bin/python -m scripts.batch_report data/raw,data/xrk docs/session_results.md`

Evaluate AI faithfulness (uses API quota): `.venv/bin/python -m scripts.faithfulness_eval data/raw docs/faithfulness_results.md 3`

## Layout

| Path | What |
|---|---|
| `backend/ingest.py` | AiM CSV and XRK/XRZ readers, validation |
| `backend/stats.py` | Cleaning (dropouts, spikes, off-tread zones), driving states, laps, per-tyre statistics |
| `backend/rules.py` | Deterministic rule engine (28 rule types) and setup sheet; flags with evidence, threshold keys and "why this matters" |
| `backend/narrative.py` | LLM debrief and Q&A (Gemini → OpenRouter free → template), faithfulness check |
| `backend/pipeline.py` | Orchestration and timings |
| `backend/storage.py` | SQLite report store |
| `backend/main.py` | FastAPI app and static frontend |
| `config/thresholds.yaml` | Every tunable threshold |
| `frontend/` | Upload page, report page, SVG charts (no external dependencies) |
| `tests/` | 76 tests on synthetic sessions with known answers |
| `CHANGES.md` | What changed since the previous version, and where |
| `docs/WEEKLY_PLAN.md` | The 4-week plan (full version: `../Tyre_Debrief_4_Week_Plan.docx`) |
| `docs/RULES.md` | Rule reference |
| `docs/DATA_NOTES.md` | Data format, audit, assumptions to confirm with Team Plus |
| `docs/session_results.md` | Output for all 17 real sessions |
| `docs/faithfulness_results.md` | Live AI fact-check evaluation (33 runs) |
| `docs/TECHNICAL.md` | Architecture, data handling, prompt design, limitations |
| `docs/REQUIREMENTS_TRACE.md` | Every brief requirement with status and evidence |
| `docs/sample_reports/` | Four real reports as PDF (one from an XRK logger file) |

## Configuration

Set these in `.env` (git-ignored) or as environment variables. Providers are tried in order;
each gets one retry with the fact-check's feedback. If none passes, a template narrative is used.

| Env var | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | unset | First narrative provider ([get a key](https://aistudio.google.com/apikey)) |
| `GEMINI_MODEL` | `gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-flash-latest` | Comma-separated chain; overloaded (503), retired (404) or rate-limited models fall through to the next |
| `OPENROUTER_API_KEY` | unset | Fallback provider ([get a key](https://openrouter.ai/keys)) |
| `OPENROUTER_MODEL` | `openrouter/free` | OpenRouter's router across its free models |
| `DEBRIEF_LLM_BUDGET_S` | `40` | Time budget for the background AI debrief (the report itself opens in about 2 s) |
| `DEBRIEF_QA_BUDGET_S` | `20` | Time budget for answering a question |
| `DEBRIEF_DISABLE_LLM` | unset | Set to `1` to force template mode |
| `DEBRIEF_DB` | `data/reports.db` | SQLite path |
