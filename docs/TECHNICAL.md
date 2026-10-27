# Technical documentation

## Architecture

The design is three-tier, as in proposal §4.1. Each stage is a separate module, so each can be tested on its own.

| Stage | Module | Input → output | Deterministic? |
|---|---|---|---|
| Ingestion | `backend/ingest.py` | AiM CSV or XRK/XRZ logger file → metadata + 20 Hz DataFrame | Yes |
| Statistics | `backend/stats.py` | DataFrame → per-tyre, per-lap and cross-tyre statistics | Yes |
| Rule engine | `backend/rules.py` + `config/thresholds.yaml` | statistics + car details → ranked flags with evidence | Yes |
| Setup sheet | `backend/rules.py` (`setup_sheet`) | flags → per-tyre pressure, camber, heat shape, tools | Yes |
| Narrative and Q&A | `backend/narrative.py` | flags + summary statistics → plain-English debrief; answers to questions | No (LLM), so it is fact-checked |
| Presentation | `backend/main.py`, `frontend/` | report JSON → web page / PDF | Yes |

Traceability runs from a sentence in the debrief, to the flag it cites, to that flag's evidence numbers and threshold keys, to the statistics. On the report page, each finding has a plain-English "why this matters" and an expandable "the numbers behind it" panel.

## Data handling

- **Driving states.** Straights are samples above 60 km/h with |lateral g| < 0.15 **and** |longitudinal g| < 0.3, so braking and acceleration zones don't distort the straight-line camber reading. Loaded corners are samples with |lateral g| > 0.6; the sign gives the direction (positive = right-hander, which loads the left tyres). The sign of lateral g matches the GPS heading rate (r = 0.96) and is present in both file formats.
- **Views.** Every tyre has its own average, peak, window share, tread profile and per-zone peaks for all running, straights and loaded corners. The report's cards update when the view changes.
- **Peaks** are the hottest temperature *held for at least 0.5 s* (rolling mean over 10 samples at 20 Hz), so single-sample blips don't count. This applies to the tyre peak, the corner peak and each zone.
- **Pressure.** TPMS readings while parked are erratic (e.g. 15 → 20 → 14 psi within two minutes), so a true cold pressure can't be read from the data. The app reports the median on the **first timed lap** and the **hot** median on flying laps. Recommendations are given as a change to the cold pressure, and as an exact new cold pressure when the racer enters the one they set.
- **Driver style.** Per lap: full throttle %, coasting % (neither throttle nor brake), trail braking (% of braking time with |lateral g| > 0.5), peak braking and cornering g. Braking is detected relative to each session's own maximum brake pressure, because CSV and XRK use different units; if there's no throttle or brake channel, G-force is used. The best lap is compared with the median flying lap.
- **XRK files** are decoded with `libxrk` (MIT licence) and resampled to 20 Hz. Against Race Studio's CSV of the same session, tyre temperatures, ambient and sensor distance are identical, and laps, best lap and the full report match.
- **Recordings with no track running** (less than 60 s above 40 km/h, e.g. paddock recordings) are rejected with a clear message.
- **Laps.**
  - Laps are split from the beacon markers. The out-lap and the in-lap are dropped.
  - Laps shorter than 60% of the median lap are treated as beacon glitches.
  - A lap more than 15% slower than the best lap counts as "slow" (pit stop, cool-down) and starts a new stint.
  - The first 2 laps of each stint are tyre warm-up laps; the rest are flying laps.
- **Window statistics** (averages, peaks, share of time in 60–90 °C, tread profiles) use flying laps when there are at least 3, so out-laps don't make a working tyre look cold.
- **Tread display.** Each tyre is drawn as seen from behind the car: left tyres read outside → inside and right tyres inside → outside, so inside edges face the middle.
- **Cleaning.**
  - Readings of 0 or outside 5–150 °C are dropped.
  - Spikes more than 15 °C from a 1 s rolling median are dropped.
  - An edge zone at least 10 °C colder than a flat tyre centre is reading the sidewall. It is excluded and reported as a sensor-alignment note.
  - A TPMS channel that repeats one value for more than 90% of samples is a frozen sensor and is ignored.
- **Privacy.**
  - Uploaded files are processed in memory and never stored; only the derived report is saved.
  - Report ids are random UUIDs. There is no endpoint that lists all reports: each browser keeps its own report ids and asks only for those.

## Prompt design

The LLM gets a *facts* object: session metadata, car details, lap summary, per-tyre summary and the list of flags. It never sees raw telemetry. Shares are given to it as whole percentages, after a live model wrote a 0.749 share as "749%".

The system prompt (`SYSTEM_PROMPT` in `narrative.py`) tells the model to:
- use only the facts;
- write every number as it appears in the facts;
- explain each technical term in plain words;
- keep each flag's hedged causal wording;
- restate the action of the rule engine's priority flag as the single takeaway;
- return one JSON object: headline, summary, one note per tyre, takeaway, takeaway flag id, cited flag ids.

**Fact check** (`check_faithfulness`). A draft is rejected if:
- any number in it is not in the facts (allowing roundings and lap-time formats);
- its takeaway flag differs from the rule engine's;
- it cites an unknown flag;
- it doesn't cover all four tyres exactly once;
- it states a cause definitely ("due to", "because", "caused by") that no flag states, unless the sentence is hedged ("likely because", "partly due to");
- it contains garbled characters.

A rejected draft is retried once with the reasons.

**Provider chain.**
- Gemini runs first, through a model list (`gemini-flash-lite-latest`, then `gemini-3.5-flash-lite`, then `gemini-flash-latest`). An overloaded (503), retired (404) or rate-limited (429) model falls through to the next.
- OpenRouter's free router runs next.
- The deterministic template runs last.
- The report does not wait for the AI. It opens in about 2 s with the template debrief, and the AI debrief is written in the background (40 s budget) and swapped in on the page when ready. This keeps CSV-to-report well under the 15 s target even when the AI service is slow (a single request varied from 2.8 to 12.3 s in testing).

**Ask about this session** (`answer_question`). Questions go through the same provider chain with a 20 s budget. The model gets the report's facts, setup sheet, driver style and per-lap summary, and its own prompt (`QA_PROMPT`). The answer passes the same number and causal checks; numbers from the question itself are allowed. If the data can't answer, it says so: for example, "What tyre brand should I buy?" is answered as not something this session can tell.

**Measured** (`docs/faithfulness_results.md`, 33 runs over 11 real sessions):
- 100% of reports used an AI narrative;
- 73% passed the fact check on the first try, and every rejected draft was fixed by the retry or the backup model; all 11 rejections were unhedged causal claims ("due to", "because");
- AI debrief time was 2.7 s at the median and 5.5 s at p95 (in the background; the report itself opens in about 2 s).

## Known limitations

1. **Data format.**
   - AiM CSV exports and AiM XRK/XRZ logger files are supported. These are the formats Team Plus supplied.
   - TeleDash and RaceChrono exports need sample files before support can be added.
   - Pressure: the XRK file stores TPMS in bar, and Race Studio's CSV value is exactly bar × 14.5038² (the bar→psi conversion applied twice), so the CSV is read as raw ÷ 14.5038. This gives realistic 27 → 30 psi warm-up curves. Zone orientation (zone 01 faces the inside) is an assumption. Both are config values pending Team Plus confirmation.
2. **Thresholds** come from Team Plus's guidance notes and haven't yet been reviewed by Team Plus against these sessions. There is a single 60–90 °C window for all compounds.
3. **Corner detection** uses lateral g (its sign gives the direction). It doesn't model weight transfer per tyre, and camber advice is based on the loaded (outside) tyre only.
4. **The fact check is structural, not semantic.** It catches invented numbers, wrong takeaways and overstated causes. It cannot judge whether a correctly-numbered sentence is misleading in tone, so a human review of sample reports is still part of validation (proposal §9.3).
5. **Single session only.** There are no multi-session trends or user accounts; both are out of scope (proposal §1.4).
6. **Driver analysis** covers warm-up cost, lap consistency, grip use, full throttle, coasting and trail braking, compared with your own best lap. There is no racing-line, braking-point or track-map analysis.
7. **Free-tier LLMs.** Gemini's free tier can be overloaded or rate-limited. When that happens the template debrief stays, so a report is always produced.
8. **Default hot-pressure target.** Without the racer's own target, 32 psi is used (config). This is a typical track-tyre figure, not specific to every tyre; the report says when the default is used.
9. **Straight-line camber tell.** In the Winton data the inside edge was rarely more than a few °C warmer on straights, so this tell fires on most tyres. That matches Team Plus's review of these sessions, but the 15/10 °C targets should be confirmed for this car and sensor.
