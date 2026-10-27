# 4-week plan

Full version with each person's progress, blockers, decisions and update scripts:
`Tyre_Debrief_4_Week_Plan.docx` (next to this repository).

| Week | Dates (2026) | Theme | Update lead |
|---|---|---|---|
| 1 | Thu 8 Oct – Wed 14 Oct | Data, file reading (CSV and AiM XRK) and project setup | Himesh |
| 2 | Thu 15 Oct – Wed 21 Oct | Statistics and rule engine | Love |
| 3 | Thu 22 Oct – Wed 28 Oct | AI debrief, fact check and report screens | Owais |
| 4 | Thu 29 Oct – Wed 4 Nov | Testing, Team Plus review, handover: complete | Himesh |

## Who does what

| Person | Role | Responsible for |
|---|---|---|
| Himesh | Project Manager, Quality Checker | Team Plus and supervisor contact; data collection and audit; tests and CI; requirements traceability; usability test; handover |
| Love | AI / Data Lead | CSV and XRK readers; cleaning and statistics; rule engine and config; AI debrief, fact check, AI evaluation |
| Owais | Frontend / UI, Documentation | Upload and report pages; API, storage and history; README and technical docs |

## Status by week

- **Week 1 (done):**
  - 22 real files checked: 11 track sessions usable, 10 rejected with reasons (6 no tyre data, 4 paddock recordings).
  - CSV and XRK readers built.
  - Pressure unit corrected after comparing XRK with CSV (CSV = bar × 14.5038², so real pressures are about 27 → 30 psi).
- **Week 2:**
  - 28 rule types from Team Plus's guidance and their review feedback.
  - Every finding traceable to its evidence and a config threshold.
  - Tread charts in TeleDash colours.
- **Week 3:**
  - Fact-checked AI debrief: 33/33 live reports got an AI debrief, 73% passed the check first time (the rest were fixed by the retry), about 2.7 s typical, written in the background so the report opens in about 2 s.
  - Full report page, PDF export, phone layout, per-browser history.
- **Week 4:**
  - Usability test.
  - Team Plus review of thresholds and the pressure correction.
  - GitHub push and handover; final demo.

Open items for Team Plus: confirm pressure units and sensor zone direction; explain the 6 empty sessions; send TeleDash/RaceChrono samples.
