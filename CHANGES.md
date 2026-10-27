# What changed

Changes since the previous zip (13 October 2026). 76 automated tests pass (was 59).

## 1. Team Plus review feedback

| Feedback | What changed | Where |
|---|---|---|
| Flip inside/outside on the tyre diagram | Each tyre is drawn as seen from behind the car: left tyres read outside → inside, right tyres inside → outside | `frontend/js/charts.js` (`zones`), `frontend/js/report.js` |
| Higher starting pressure; use logic for choices | One pressure recommendation per tyre, combining tread heat shape with measured hot pressure against a target (entered on the form, or 32 psi default). The finding shows the reasoning. Conflicting signals give "hold and check" (`PRESSURE_CONFLICT`) | `backend/rules.py` (`pressure_rules`), `config/thresholds.yaml` (`pressure.target_hot_psi`) |
| Camber tell when the inside isn't ~15 °C warmer on straights | New finding `CAMBER_STRAIGHT_LOW` (15 °C front, 10 °C rear) | `backend/rules.py` (`camber_rules`) |
| Peak temperature in loaded corners | "Corner peak" on each tyre card; peak marker on every zone | `backend/stats.py`, `frontend/js/charts.js`, `frontend/js/report.js` |
| Peak = hottest held at least 0.5 s | All peaks are 0.5 s held maxima | `backend/stats.py` (`_held_max`), `config/thresholds.yaml` (`peak_hold_s`) |
| Fix averaging for corners and straights | Each view (all / straights / corners) has its own average, peak and in-window %; the cards update when you switch. Straights exclude braking and acceleration zones | `backend/stats.py` (`views`), `config/thresholds.yaml` (`straight_max_lon_g`), `frontend/js/report.js` |
| Diagram of changes, e.g. "left front up by x psi" | New "Before your next session" section: car diagram with ▲/▼ pressure, camber change and heat-shape colouring | `frontend/js/charts.js` (`setup`), `frontend/js/report.js` |
| Suggestions before next session: pressure, camber, tools or not, heat shape | Setup sheet table per tyre: pressure, camber, heat shape (over/under-inflated, inside/outside hot, even), tools needed | `backend/rules.py` (`setup_sheet`, `heat_shape`), `backend/pipeline.py` |
| Tell more about why a change is needed | "Why this matters" on every finding | `backend/rules.py` (`WHY`), `frontend/js/report.js` |
| Be able to ask questions | "Ask about this session" box with suggested questions; answers are fact-checked against the session and say when the data can't answer | `backend/narrative.py` (`answer_question`, `QA_PROMPT`), `backend/main.py` (`POST /api/reports/{id}/ask`), `frontend/js/report.js` |
| Driver style notes | New "Driver style" section: full throttle, coasting, trail braking, peak braking/cornering g, best lap vs typical lap, with tips (`DRIVER_BEST_LAP_STYLE`, `DRIVER_COASTING`) | `backend/ingest.py` (throttle and brake channels), `backend/stats.py`, `backend/rules.py`, `frontend/js/report.js` |
| Tidy up | Matching findings on both tyres of an axle merged into one (about 10 → 6.5 per report); driver notes moved to their own section | `backend/rules.py` (`merge_axles`), `frontend/js/report.js` |
| Track map | Not done (decided against) | — |

## 2. Other improvements

- **Report opens in about 2 s.** The AI debrief is written in the background and appears on the page when ready, instead of the report waiting for the AI (`backend/main.py`, `backend/pipeline.py` `complete_narrative`, `backend/storage.py` `update_narrative`, `frontend/js/report.js`).
- **Fact check allows hedged causes.** "Likely because…" is allowed; definite claims like "because" or "due to" are still rejected unless a finding says so (`backend/narrative.py`).
- **Pressures** are shown as first timed lap → hot on flying laps, because TPMS readings while parked are unreliable (`backend/stats.py`).
- **"No tyre data" errors** now say what went wrong: sensors never logged, only logged while parked, or a paddock recording. Only time on track is checked, so a long pit stay no longer causes a wrong rejection (`backend/pipeline.py` `session_problem`).
- **Sample picker** groups usable track sessions separately from files that can't be analysed, with the reason (`backend/main.py`, `frontend/js/upload.js`).
- **Phone layout:** the setup table turns into cards on small screens (`frontend/css/app.css`).
- **Deep link to a view,** e.g. `/report?id=…&view=corner` (`frontend/js/report.js`).

## 3. Setup and installation

- **New `SETUP.md`:** step-by-step guide for a new Mac.
- **Pinned `starlette` and `pyarrow`** so every install gets the tested versions (`requirements.txt`).
- **Windows fix:** the scripts write UTF-8 files (`scripts/batch_report.py`, `scripts/faithfulness_eval.py`, `backend/pipeline.py`).
- **The GitHub test workflow** now runs on macOS, Windows and Linux with Python 3.12 and 3.13 (`.github/workflows/tests.yml`).

## 4. Docs and results refreshed

- `docs/RULES.md`: now 28 rule types, the setup sheet, and merging.
- `docs/TECHNICAL.md`: views, held peaks, pressures, driver style, Q&A, background debrief, new limitations.
- `docs/REQUIREMENTS_TRACE.md`: new table mapping each review feedback item to what was done.
- `docs/faithfulness_results.md`: 33/33 AI debriefs, 73% passed first time, 2.7 s typical.
- `docs/session_results.md` and `docs/sample_reports/` (4 PDFs) regenerated with the new version.

## Still to confirm with Team Plus

- 32 psi default hot target.
- 15 °C / 10 °C straight-line camber targets.
- Pressure unit and sensor zone direction (unchanged from before).
