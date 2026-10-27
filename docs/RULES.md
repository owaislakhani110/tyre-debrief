# Rule reference

All thresholds live in `config/thresholds.yaml`. Each flag in a report lists the keys it tested and carries a
plain-English "why this matters" explanation.

When both tyres on one axle get the same camber or pressure finding, the two are merged into one
("Front tyres: …"), with each tyre's numbers kept in the text and the evidence.

| Rule | Severity | Fires when | Advice | Source |
|---|---|---|---|---|
| `TEMP_BELOW_WINDOW` | high if < 25% in window, else medium | a tyre is in 60–90 °C less than 50% of flying-lap time and mostly below | Build heat on the out-lap; a softer compound if still cold once pressures are right | Team Plus notes §1 |
| `TEMP_ABOVE_WINDOW` | high | > 30% of time above 90 °C | Cool-down lap; check pressures aren't low | Team Plus notes §1 |
| `CAMBER_ADD` | high if straight inside−outside is also below target, else medium | loaded tyre in corners is > 6 °C hotter on the **outside** edge | Increase negative camber 0.25–0.5° | Team Plus notes §2, camber chart "More camber possible" |
| `CAMBER_REDUCE` | high if straight inside−outside is also above target, else medium | loaded tyre in corners is > 6 °C hotter on the **inside** edge | Decrease negative camber 0.25–0.5° | Team Plus notes §2, camber chart "Too much camber" |
| `CAMBER_STRAIGHT_LOW` | medium | corners even, but on straights the inside is not at least target − 5 °C warmer than the outside (target 15 °C front, 10 °C rear) | Add about 0.25° negative camber | Team Plus notes §1; Team Plus review feedback ("tell for camber if inside isn't ~15 warmer on straights") |
| `CAMBER_INNER_HOT_STRAIGHT` | low | corners even, but straight inside−outside > target + 8 °C | Watch inside-edge wear | Team Plus notes §1 |
| `CAMBER_OK` | info | loaded tyre within 6 °C across its width and the straight-line spread is near target | none | Team Plus camber chart "Effective camber" |
| `PRESSURE_HIGH` | medium | tread centre > 5 °C hotter than the edges (over-inflated shape), and the hot pressure does not contradict it | Lower cold pressure; by the miss to target if known, else 1.5 psi | Team Plus notes §1 |
| `PRESSURE_LOW` | medium | tread centre > 5 °C cooler than the edges (under-inflated shape), and the hot pressure does not contradict it | Raise cold pressure; by the miss to target if known, else 1.5 psi | Team Plus notes §1 |
| `PRESSURE_TARGET` | medium | tread shape even, but the flying-lap hot pressure misses the target (entered, or 32 psi default) by > 1 psi | Raise/lower the cold pressure by the miss; exact new cold pressure if the racer entered theirs | Team Plus notes §4; review feedback ("higher starting pressure, use logic for choices") |
| `PRESSURE_CONFLICT` | low | tread shape and hot pressure point in opposite directions | Keep the cold pressure; check the tyre's hot target | Avoids contradictory advice |
| `PRESSURE_BUILD` | info | TPMS data present | First timed lap → hot (flying laps) pressure per tyre | Team Plus notes §4 |
| `PRESSURE_AXLE_SPLIT` | medium | hot pressures on one axle differ by > 2 psi | Set cold pressures equal; check for a slow leak | Scope sheet ("temperature **and pressure** data") |
| `BALANCE_FRONT_HOT` / `BALANCE_REAR_HOT` | low | front/rear average differs by > 8 °C (+4 °C allowance on the driven axle) | Understeer / oversteer hint | Team Plus notes §5, §7 |
| `BALANCE_SIDE` | info | left/right differ by > 8 °C | Explained by the corner-direction mix (track layout) | Team Plus notes §5 |
| `SUSPENSION_HINT` | low | a balance flag fires but no camber or pressure flag explains it on the hotter axle | Anti-roll bar / ride-height change, one at a time | Team Plus notes §3 |
| `TREND_HEATING` / `TREND_COOLING` | info | average changes > 6 °C between the first and last third of running | none | Team Plus notes §4 |
| `WARMUP` | info | always, with laps | Lap where all four tyres first reached the window | Team Plus notes §4 |
| `WARMUP_COST` | info | warm-up laps > 1 s slower than flying laps | "That's the tyres, not you" | Team Plus notes §5 (driver vs tyre) |
| `DRIVER_CONSISTENCY` | low | flying-lap standard deviation > 1.0 s | Judge setup changes on consistent runs | Team Plus notes §5 |
| `DRIVER_GRIP_USE` | low | best lap's peak braking or cornering g is > 0.05 g above a typical flying lap | Repeat best-lap effort consistently | Team Plus notes §7 (G-force); scope "driver tips" |
| `DRIVER_BEST_LAP_STYLE` | low | best lap differs from a typical flying lap by ≥ 3 points of full throttle, ≥ 1 point less coasting, or ≥ 5 points of trail braking | The habit that found the time, e.g. "get back to full throttle earlier" | Review feedback ("driver style notes"); scope "driving technique" |
| `DRIVER_COASTING` | low | a typical flying lap has > 5% coasting (neither throttle nor brake) and the best-lap note didn't already cover it | Go straight from brake to throttle | Review feedback ("driver style notes") |
| `BEST_LAP` | info | always, with laps | Tyre temperatures on the best lap | Team Plus notes §4 |
| `DATA_SENSOR_ALIGNMENT` | info | an edge zone ≥ 10 °C below a flat centre | Check Wheel Turtle aim | Data audit |
| `DATA_NO_PRESSURE` | info | TPMS missing or frozen for a tyre | Pressure advice from temperatures only | Data audit |

**Takeaway selection:** the highest-priority flag (severity weight × 100 + magnitude) that has an action.

**Setup sheet** ("Before your next session"): built from the flags above. For each tyre:
- a pressure change, plus the exact cold pressure if the racer entered theirs;
- a camber change;
- the tread heat shape (hot centre, hot edges, hot inside or outside edge, or even);
- whether tools are needed: pressure needs a gauge and air only, while camber and suspension need tools.

**Not implemented** (candidates for after handover):
- multi-session trends (Team Plus notes §4; out of scope per proposal §1.4);
- a track map following the car (review feedback; decided against for now);
- racing-line and braking-point analysis (scope sheet "desirable"; needs GPS track mapping);
- per-tyre load estimation from G-force (§7). G-force is currently used to separate driving states, compare grip use between laps, and detect trail braking.
