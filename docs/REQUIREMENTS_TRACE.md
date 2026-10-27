# Requirements traceability

Every requirement from the three briefs, with its status and where the evidence is.
Status key: ✅ done · 🟡 partly done · ⏳ planned (team activity, Part 4) · ⛔ out of scope by agreement.

## 1. Team Plus project scope sheet (2026-S2-06)

| Requirement | Status | Evidence |
|---|---|---|
| Learn existing functionality and data from Team Plus sensors and logging tools | ✅ | `docs/DATA_NOTES.md` (17-session audit, channel map, assumptions) |
| Prototype web app that imports a session and gives driver advice to improve lap times | ✅ | `backend/`, `frontend/`; `docs/sample_reports/*.pdf` |
| **Minimum:** AI advice on tyre pressure and camber from tyre temperature and pressure data | ✅ | Rules `CAMBER_ADD/REDUCE/OK`, `PRESSURE_HIGH/LOW` (temperature), `PRESSURE_AXLE_SPLIT`, `PRESSURE_TARGET` (TPMS) |
| Desirable: driver braking performance | 🟡 | Driver style section: peak braking g and trail braking per lap, best vs typical (`DRIVER_GRIP_USE`, `DRIVER_BEST_LAP_STYLE`). No braking-point analysis |
| Desirable: racing line | ⛔ | Needs GPS track mapping; listed in `docs/TECHNICAL.md` limitations |
| Desirable: other driver tips to improve lap time | ✅ | Driver style notes from throttle, brake and G-force: full throttle, coasting, trail braking (`DRIVER_BEST_LAP_STYLE`, `DRIVER_COASTING`); `WARMUP_COST`, `DRIVER_CONSISTENCY`, `DRIVER_GRIP_USE` |
| Deliver code and documentation in a GitHub repository | 🟡 | Repository ready with README, docs and CI (`.github/workflows/tests.yml`); push to GitHub pending |
| Formal handover to the sponsor | ⏳ | Part 4 |
| Test on the Team Plus car at a closed-road session (if organised) | ⏳ | Depends on Team Plus; app is ready to take the exports |

## 2. Team Plus tyre performance / AI analysis notes

| Note | Status | Evidence |
|---|---|---|
| §1 Benchmark rule engine for temperature and pressure | ✅ | `config/thresholds.yaml`, `backend/rules.py` (28 rule types) |
| §1 Ideal window 60–90 °C across the session | ✅ | `TEMP_BELOW_WINDOW`, `TEMP_ABOVE_WINDOW`; judged on flying laps |
| §1 Even temperatures across a well-set-up tyre | ✅ | 8-zone tread profiles per tyre; `CAMBER_OK` |
| §1 Straights: inside ~15 °C hotter on the front, ~10 °C on the rear | ✅ | `CAMBER_STRAIGHT_LOW` (tell when the inside is not warmer), `CAMBER_INNER_HOT_STRAIGHT`; straights exclude braking/acceleration |
| §1 High middle = over-pumped, low middle = under-pumped | ✅ | `PRESSURE_HIGH`, `PRESSURE_LOW` |
| §1 Analyse the whole session, not one point in time | ✅ | Session, flying-lap and per-lap statistics |
| §1 Stick to the compound in Team Plus's data | ✅ | Single window for the supplied BMW F80 data; compound captured on the form |
| §2 Camber on straights vs corners; weight transfer in corners | ✅ | Straight and loaded-corner views with their own averages and held peaks (outside tyre detected from lateral g) |
| §2 Recommend "increase / decrease camber" | ✅ | `CAMBER_ADD`, `CAMBER_REDUCE` with 0.25–0.5° steps |
| §3 Suspension / ride height when pressure and camber can't explain it | ✅ | `SUSPENSION_HINT` |
| §4 Track lap times; improving, declining or consistent | ✅ | Lap chart and table; `TREND_*`, `DRIVER_CONSISTENCY` |
| §4 Start vs end condition → future pressure recommendation | ✅ | `PRESSURE_BUILD`; `PRESSURE_TARGET` gives a recommended cold pressure |
| §4 Trends across multiple session days | ⛔ | Out of scope (proposal §1.4) |
| §5 Separate driver vs pressure vs camber vs temperature vs track effects | 🟡 | Flags categorised by cause; `WARMUP_COST` (tyres, not driver); `BALANCE_SIDE` (track layout). Not a full causal model |
| §6 Raw data → actionable advice ("inside hotter → reduce camber") | ✅ | Every actionable flag has a plain-English action; one priority takeaway |
| §7 G-force: cornering load, weight transfer, setup vs driving | ✅ | Lateral and longitudinal g drive the straight/corner split; grip use and trail braking per lap |

## 3. Team Plus review feedback (October 2026)

| Feedback | Status | What was done |
|---|---|---|
| Higher starting pressure; use logic for choices | ✅ | One pressure recommendation per tyre, combining tread shape and measured hot pressure against a target (entered or 32 psi default). The logic is shown in the finding. Conflicting signals give "hold and check" instead of contradictory advice |
| Flip inside and outside on the diagram | ✅ | Tread charts drawn as seen from behind the car: left tyres outside → inside, right tyres inside → outside |
| Tell for camber when the inside isn't ~15 °C warmer on straights | ✅ | `CAMBER_STRAIGHT_LOW` |
| Peak temperature for loaded corners | ✅ | "Corner peak" on every tyre card; per-zone peak markers |
| Fix averaging for corners and straights | ✅ | Each view has its own average, peak and window share; straights exclude braking and acceleration |
| Diagram showing e.g. "left front up by x psi"; visual of changes | ✅ | "Before your next session" car diagram with ▲/▼ pressure, camber change and heat-shape colouring |
| Suggestions before next session: pressure, camber, tools or not, heat shape (over/under-inflated) | ✅ | Setup sheet table: pressure, camber, heat shape, tools |
| Tell more in findings about why the change is needed | ✅ | "Why this matters" on every finding |
| Be able to ask questions | ✅ | "Ask about this session", fact-checked against the session's data |
| Suggested actions; tidy up functionality | ✅ | Setup sheet; same-axle findings merged (10 → 7 on Saturday practice); driver notes in their own section; report opens in ~2 s with the AI debrief arriving in the background |
| Peak = hottest held for at least 0.5 s | ✅ | All peaks are 0.5 s held maxima |
| Driver style notes | ✅ | Driver style section: best lap vs typical lap |
| Track map following the car | ⛔ | Decided against for now |

## 4. Project proposal (9785, 2026-S2-06)

### Objectives and user stories

| Item | Status | Evidence |
|---|---|---|
| Obj 1 / US01: import real exports, clear errors, no manual prep | ✅ | 22 real files (CSV and XRK): 11 track sessions analysed, 10 rejected with reasons (6 no tyre data, 4 paddock recordings); `tests/test_ingest.py`, `tests/test_xrk.py` |
| Obj 2 / US02: per-tyre statistics, repeatable | ✅ | `backend/stats.py`; `test_deterministic`; known-answer tests |
| Obj 3 / US03: rule engine, traceable flags, configurable thresholds | ✅ | Evidence and threshold keys on every flag; YAML config |
| Obj 4 / US04: plain-English debrief, verified facts only, one takeaway | ✅ | `backend/narrative.py` fact check; `docs/faithfulness_results.md` |
| Obj 5 / US05: one-page report in a browser | ✅ | `frontend/report.html`; PDF export |
| Obj 6: check accuracy and usefulness for non-experts | 🟡 | Accuracy: tests and faithfulness evaluation. Usefulness: user test pending (Part 4) |

### Functional requirements

| FR | Status | Evidence |
|---|---|---|
| FR1 CSV upload | ✅ | Upload page accepts CSV and the logger's XRK/XRZ file; `POST /api/reports` |
| FR2 Car context form | ✅ | Make, model, drivetrain, compound, camber, cold and target pressures, session type, notes |
| FR3 Extract temperature, distance, timestamp | ✅ | `ingest.py` (all 32 zones, sensor distance, time, TPMS, GPS) |
| FR4 Per-tyre average, peak, inner/outer delta | ✅ | `stats.py` |
| FR5 Front/rear and left/right comparisons | ✅ | `axle` statistics; `BALANCE_*` |
| FR6 Rule-based flags | ✅ | 28 rule types |
| FR7 LLM narrative with a single takeaway | ✅ | Gemini → OpenRouter → template, fact-checked |
| FR8 Report with per-tyre summaries and visuals | ✅ | Car overview, 8-zone charts, lap charts |
| FR9 Saved reports | ✅ | SQLite; per-browser history |
| FR10 Invalid or broken CSVs reported properly | ✅ | `IngestError` messages, including corrupt XRK and paddock recordings; `test_api.py` |

### Non-functional requirements

| NFR | Target | Result |
|---|---|---|
| Performance | ~15 s CSV to report | 2.0–6.2 s on real sessions, including the AI narrative |
| Usability | No unexplained jargon | Prompt requires plain-word explanations; user test pending |
| Reliability | Same input, same analysis | Deterministic stats and rules (`test_deterministic`) |
| Security / privacy | Reports not visible to other users | Random UUID ids, no list-all endpoint, raw CSVs not stored |
| Maintainability | Thresholds not hard-coded | `config/thresholds.yaml`, re-read on every report |
| Availability | Demo-ready weeks 8–10 | Runs locally with one command; works offline (template mode) |

### Deliverables (§4.6)

| Deliverable | Status | Evidence |
|---|---|---|
| Working site: upload, form, report, history | ✅ | `frontend/` |
| CSV parser tested on Wheel Turtle / TeleDash / RaceChrono exports | 🟡 | Tested on 17 AiM CSV exports **and AiM XRK logger files** (decoded and checked against the CSV of the same session); TeleDash/RaceChrono samples requested from Team Plus |
| Rule engine and configurable thresholds file | ✅ | `rules.py`, `thresholds.yaml`, `docs/RULES.md` |
| Prompt templates | ✅ | `SYSTEM_PROMPT` in `narrative.py`; `docs/TECHNICAL.md` |
| Sample reports from real data | ✅ | `docs/sample_reports/` (4 PDFs, one from an XRK file) |
| Technical docs: data format, rule logic, prompt design, limitations | ✅ | `docs/DATA_NOTES.md`, `docs/RULES.md`, `docs/TECHNICAL.md` |

### Quality assurance (§9)

| Item | Status | Evidence |
|---|---|---|
| Unit tests: parsing, statistics, rules | ✅ | 76 automated tests (`pytest`), CI workflow |
| Integration tests: CSV → stats → rules → LLM → report | ✅ | `tests/test_api.py`; live run of all 22 real files |
| System tests: valid, malformed and missing data; LLM failure | ✅ | Bad-file tests; provider-failure and time-budget tests |
| Faithfulness review of AI statements | ✅ | Automated check on every report; 33-run evaluation |
| User validation by a non-team member | ⏳ | Part 4 |
| Team Plus domain review of thresholds | ⏳ | Part 4 |

### Risks (§7): how each was handled

| Risk | Mitigation in the build |
|---|---|
| R1 CSV inconsistencies | Defensive parser; real-file edge cases handled (metadata "Time" row, truncated names, zero channels, spikes, frozen TPMS, double-converted pressure units, paddock recordings) |
| R2 Thresholds wrong | All thresholds in YAML; each flag cites its keys; Team Plus review planned |
| R3 LLM misrepresents data | LLM sees only verified facts; fact check plus retry plus template fallback; measured in the evaluation |
| R4 No real data | Real Team Plus data used throughout; synthetic generator for tests |
| R7 Scope creep | Stretch features limited to per-lap trends and driver grip use |
| R9 LLM cost / rate limits | Free models; model fallback chain; 11 s budget; template fallback |
| R10 Data privacy | No list-all endpoint; raw CSVs not stored; UUID report ids |

## Open items (needed for a complete hand-in)

1. **Team Plus** to confirm the pressure unit (we read the CSV as bar × 14.5038², based on the XRK), zone orientation, and why 6 sessions have zero tyre data; to send TeleDash/RaceChrono sample exports; and to review the thresholds.
2. **User test** with one person outside the team (proposal §9.2).
3. **Push to GitHub** and do the formal handover.
