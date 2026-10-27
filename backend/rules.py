from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .stats import CORNERS, FRONT, REAR

NAMES = {"LF": "left-front", "RF": "right-front", "LR": "left-rear", "RR": "right-rear"}


@dataclass
class Flag:
    rule: str
    category: str
    severity: str
    title: str
    detail: str
    action: str | None
    tyres: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    magnitude: float = 0.0
    merge: dict = field(default_factory=dict)

    def to_dict(self, weights: dict) -> dict:
        d = asdict(self)
        d.pop("merge")
        d["priority"] = weights.get(self.severity, 0) * 100 + min(self.magnitude, 99)
        d["why"] = WHY.get(self.rule, "")
        return d


WHY = {
    "TEMP_BELOW_WINDOW": "Tyres only grip properly inside their working temperature range. Below it the rubber is too hard to key into the track, so there is less grip under braking and in corners.",
    "TEMP_ABOVE_WINDOW": "Above the working range the rubber overheats and goes greasy, so grip drops away and the tyre wears quickly.",
    "CAMBER_ADD": "Camber is the inward tilt of the wheel. In a corner the car rolls and pushes the tyre onto its outside edge; negative camber counters that so the whole tread grips. A hotter outside edge when loaded means the tyre is rolling onto its shoulder.",
    "CAMBER_REDUCE": "Too much negative camber leaves the tyre leaning on its inside edge even in corners, so only part of the tread grips and the inside edge wears out.",
    "CAMBER_STRAIGHT_LOW": "With negative camber the inside edge carries more load on straights, so Team Plus expects it to run about 15 °C (front) or 10 °C (rear) warmer than the outside. A flat spread on straights means the tyre is running almost upright, so there is room for more negative camber.",
    "CAMBER_INNER_HOT_STRAIGHT": "A very hot inside edge on straights wears the inside shoulder faster, even when the tyre looks even in corners.",
    "CAMBER_OK": "When the tyre is loaded in a corner, an even temperature across the tread means the whole contact patch is working.",
    "PRESSURE_HIGH": "Too much air makes the tyre crown, so the centre carries the load and runs hottest while the edges do little work. That means a smaller contact patch and less grip.",
    "PRESSURE_LOW": "Too little air lets the centre of the tread lift, so the edges carry the load and run hottest. The tyre feels vague and overheats its shoulders.",
    "PRESSURE_TARGET": "Each tyre is designed to work at a particular hot pressure. Pressure rises as the tyre heats up, so the cold pressure is set lower and builds to the target on track.",
    "PRESSURE_CONFLICT": "The tread temperature shape and the measured pressure point in opposite directions, so changing pressure could make one of them worse.",
    "PRESSURE_BUILD": "Air expands as the tyre heats up, so pressure climbs over the first laps and then settles.",
    "PRESSURE_AXLE_SPLIT": "Tyres on the same axle should run the same pressure. A difference makes the car behave differently turning left and right, and can mean a slow leak.",
    "BALANCE_FRONT_HOT": "The tyres that work hardest get hottest. Hotter fronts mean the front is doing more of the work, which usually feels like understeer.",
    "BALANCE_REAR_HOT": "The tyres that work hardest get hottest. Hotter rears mean the rear is doing more of the work, which usually feels like oversteer or wheelspin.",
    "BALANCE_SIDE": "Tracks with more corners in one direction load one side of the car more, so that side runs hotter. That is normal, not a setup problem.",
    "SUSPENSION_HINT": "If pressure and camber look right but one end of the car still works harder, the balance usually comes from the suspension: anti-roll bars and ride height decide how load is shared front to rear.",
    "TREND_HEATING": "A steady rise through the session means the tyres were still building heat, and pressures rise with them.",
    "TREND_COOLING": "Tyres cooling through a session usually means the pace dropped, for example in traffic or on cool-down laps.",
    "WARMUP": "Tyres need a few laps to reach their working temperature; until then there is less grip.",
    "WARMUP_COST": "Lap time on the first laps of a run is mostly about tyre temperature, so judge your driving on the laps after the tyres are warm.",
    "DRIVER_CONSISTENCY": "A setup change is only measurable if lap times are steady; a big spread hides the effect of the change.",
    "DRIVER_GRIP_USE": "Your best lap shows how much grip the car really has. Using that grip more often is free lap time.",
    "DRIVER_BEST_LAP_STYLE": "Comparing your fastest lap with a typical one shows which habits found the time.",
    "DRIVER_COASTING": "Time with neither throttle nor brake is time the car is not accelerating or slowing usefully, and the tyres cool down.",
    "DATA_SENSOR_ALIGNMENT": "A sensor zone aimed at the sidewall reads cold and would look like a camber problem, so it is left out.",
    "DATA_NO_PRESSURE": "Without pressure readings, pressure advice comes from the tread temperature shape only.",
}


def _join(corners) -> str:
    if set(corners) == set(NAMES):
        return "all four"
    if set(corners) == set(FRONT):
        return "both front"
    if set(corners) == set(REAR):
        return "both rear"
    names = [NAMES[c] for c in corners]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def temperature_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    w = cfg["temperature_window"]
    lo, hi = w["low_c"], w["high_c"]
    cold, hot = [], []
    for c in CORNERS:
        t = st["tyres"][c]
        if t["share_in_window"] is None:
            continue
        if t["share_in_window"] < w["min_share_in_window"] and t["share_below_window"] > t["share_above_window"]:
            cold.append(c)
        elif t["share_above_window"] and t["share_above_window"] > 0.3:
            hot.append(c)
    flags = []
    thresholds = {"temperature_window.low_c": lo, "temperature_window.high_c": hi,
                  "temperature_window.min_share_in_window": w["min_share_in_window"]}
    if cold:
        worst = min(st["tyres"][c]["share_in_window"] for c in cold)
        ambient = st["session"].get("ambient_c")
        amb = f" Ambient temperature was {ambient} °C, which makes heat harder to build." if ambient is not None and ambient < 18 else ""
        flags.append(Flag(
            rule="TEMP_BELOW_WINDOW", category="temperature",
            severity="high" if worst < 0.25 else "medium",
            title=f"{_join(cold).capitalize()} tyre{'s' if len(cold) > 1 else ''} ran below the {lo}–{hi} °C working window",
            detail=f"Measured over {st['lap_summary']['window_basis']}. " + " ".join(
                f"The {NAMES[c]} averaged {st['tyres'][c]['average_c']} °C and was in the window "
                f"{round(st['tyres'][c]['share_in_window'] * 100)}% of the time." for c in cold) + amb,
            action="Use the out-lap and first flying lap to build heat with firm braking and acceleration. "
                   "If the tyres still stay cold once the pressures are right, a softer compound will reach the window more easily.",
            tyres=cold,
            evidence={c: {"average_c": st["tyres"][c]["average_c"], "share_in_window": st["tyres"][c]["share_in_window"]} for c in cold}
                     | {"ambient_c": ambient},
            thresholds=thresholds, magnitude=(1 - worst) * 50))
    if hot:
        flags.append(Flag(
            rule="TEMP_ABOVE_WINDOW", category="temperature", severity="high",
            title=f"{_join(hot).capitalize()} tyre{'s' if len(hot) > 1 else ''} overheated",
            detail=" ".join(f"The {NAMES[c]} peaked at {st['tyres'][c]['peak_c']} °C and spent "
                            f"{round(st['tyres'][c]['share_above_window'] * 100)}% of the time above {hi} °C." for c in hot),
            action="Overheated tyres lose grip quickly. Consider a cool-down lap between pushes and check pressures are not too low.",
            tyres=hot,
            evidence={c: {"peak_c": st["tyres"][c]["peak_c"], "share_above_window": st["tyres"][c]["share_above_window"]} for c in hot},
            thresholds=thresholds, magnitude=60))
    return flags


def camber_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    cc = cfg["camber"]
    tol, even = cc["straight_tolerance_c"], cc["corner_even_tolerance_c"]
    flags = []
    for c in CORNERS:
        t = st["tyres"][c]
        corner = t.get("corner_loaded", {})
        straight = t.get("straight", {})
        cio = corner.get("inner_minus_outer")
        sio = straight.get("inner_minus_outer")
        if cio is None or corner.get("samples", 0) < 200:
            continue
        axle = "front" if c in FRONT else "rear"
        target = cc["straight_target_inner_minus_outer_c"][axle]
        ev = {"corner_inner_c": corner["inner"], "corner_outer_c": corner["outer"], "corner_inner_minus_outer_c": cio,
              "straight_inner_minus_outer_c": sio, "straight_target_c": target}
        th = {"camber.corner_even_tolerance_c": even, f"camber.straight_target_inner_minus_outer_c.{axle}": target,
              "camber.straight_tolerance_c": tol}
        if -cio > even:
            strong = sio is not None and sio < target - tol
            flags.append(Flag(
                rule="CAMBER_ADD", category="camber", severity="high" if strong else "medium",
                title=f"{NAMES[c].capitalize()}: more negative camber possible",
                detail=f"In corners the loaded {NAMES[c]} ran {abs(cio)} °C hotter on the outside edge "
                       f"({corner['outer']} °C) than the inside ({corner['inner']} °C), so the outer shoulder is doing too much work."
                       + (f" On straights the inside was only {sio} °C hotter than the outside (typical is about {target} °C)." if strong else ""),
                action=f"You can increase negative camber on the {NAMES[c]} (about 0.25–0.5° at a time) and re-check.",
                tyres=[c], evidence=ev, thresholds=th, magnitude=abs(cio)))
        elif cio > even:
            strong = sio is not None and sio > target + tol
            flags.append(Flag(
                rule="CAMBER_REDUCE", category="camber", severity="high" if strong else "medium",
                title=f"{NAMES[c].capitalize()}: too much negative camber",
                detail=f"Even when loaded in corners the {NAMES[c]} ran {cio} °C hotter on the inside edge "
                       f"({corner['inner']} °C) than the outside ({corner['outer']} °C)."
                       + (f" On straights the inside was {sio} °C hotter (typical is about {target} °C)." if strong else ""),
                action=f"You can decrease negative camber on the {NAMES[c]} (about 0.25–0.5° at a time) to use more of the tyre and reduce inside-edge wear.",
                tyres=[c], evidence=ev, thresholds=th, magnitude=cio))
        elif sio is not None and sio < target - cc["straight_low_tolerance_c"]:
            frag = (f"on the {NAMES[c]} it was only {sio} °C warmer" if sio > 0
                    else f"on the {NAMES[c]} the outside was {abs(sio)} °C warmer instead")
            flags.append(Flag(
                rule="CAMBER_STRAIGHT_LOW", category="camber", severity="medium",
                title=f"{NAMES[c].capitalize()}: inside edge not warmer on straights",
                detail=f"On straights the inside edge should run about {target} °C warmer than the outside. On the {NAMES[c]} "
                       + (f"it was only {sio} °C warmer" if sio > 0 else f"the outside was {abs(sio)} °C warmer instead")
                       + ", so the tyre is running almost flat and more negative camber is possible. "
                       f"In corners it was even (inside {corner['inner']} °C, outside {corner['outer']} °C), so change in small steps.",
                action=f"Add about 0.25° of negative camber on the {NAMES[c]} and check the straight-line spread moves towards {target} °C.",
                tyres=[c], evidence=ev, thresholds={**th, "camber.straight_low_tolerance_c": cc["straight_low_tolerance_c"]},
                magnitude=target - sio,
                merge={"key": "camber_low", "title": "inside edges not warmer on straights",
                       "pre": f"On straights the inside edge should run about {target} °C warmer than the outside.",
                       "frag": frag,
                       "post": "So these tyres are running almost flat and more negative camber is possible. "
                               "They were even in corners, so change in small steps.",
                       "act_all": f"Add about 0.25° of negative camber on both {{axle}} tyres and check the straight-line "
                                  f"spread moves towards {target} °C.", "act": ""}))
        elif sio is not None and sio > target + tol:
            flags.append(Flag(
                rule="CAMBER_INNER_HOT_STRAIGHT", category="camber", severity="low",
                title=f"{NAMES[c].capitalize()}: inside edge hot on straights",
                detail=f"The tyre is even in corners, but on straights the inside ran {sio} °C hotter than the outside "
                       f"(typical is about {target} °C). Watch for inside-edge wear.",
                action=None, tyres=[c], evidence=ev, thresholds=th, magnitude=sio - target))
        else:
            flags.append(Flag(
                rule="CAMBER_OK", category="camber", severity="info",
                title=f"{NAMES[c].capitalize()}: camber looks effective",
                detail=f"When loaded in corners the {NAMES[c]} was within {even} °C across its width "
                       f"(inside {corner['inner']} °C, outside {corner['outer']} °C).",
                action=None, tyres=[c], evidence=ev, thresholds=th))
    return flags


def _cold_set(ctx: dict, corner: str):
    return ctx.get("cold_pressure_front_psi" if corner in FRONT else "cold_pressure_rear_psi")


def pressure_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    shape_t, pc = cfg["pressure_from_temperature"], cfg["pressure"]
    target = ctx.get("target_hot_pressure_psi") or pc["target_hot_psi"]
    source = "your entry" if ctx.get("target_hot_pressure_psi") else "the default target; enter your tyre's own on the upload form"
    tol = pc["target_tolerance_psi"]
    flags = []
    for c in CORNERS:
        t = st["tyres"][c]
        mme = t["all"].get("middle_minus_edges")
        pr = t.get("pressure_psi") or {}
        hot, first = pr.get("hot"), pr.get("first_lap")
        shape = None if mme is None else "over" if mme > shape_t["middle_over_edges_c"] else \
            "under" if -mme > shape_t["middle_under_edges_c"] else "even"
        miss = round(hot - target, 1) if hot is not None else None
        lower = shape == "over" or (miss is not None and miss > tol)
        raise_ = shape == "under" or (miss is not None and miss < -tol)
        if not (lower or raise_):
            continue
        cold = _cold_set(ctx, c)
        name = NAMES[c]
        shape_text = {"over": f"The centre of the tread ran {mme} °C hotter than its edges, the shape of an over-inflated tyre.",
                      "under": f"The centre of the tread ran {abs(mme) if mme is not None else 0} °C cooler than its edges, the shape of an under-inflated tyre.",
                      "even": "The tread temperature was even across its width.", None: ""}[shape]
        pressure_text = (f" It ran {first} psi on the first timed lap and settled at {hot} psi hot on flying laps, against a "
                         f"{target} psi hot target ({source})." if hot is not None else " There is no pressure reading for this tyre.")
        ev = {"tread_shape": shape, "middle_minus_edges_c": mme, "first_lap_psi": first, "hot_psi": hot,
              "target_hot_psi": target, "target_source": "entered" if ctx.get("target_hot_pressure_psi") else "default",
              "miss_psi": miss, "cold_set_psi": cold}
        th = {"pressure.target_tolerance_psi": tol, "pressure_from_temperature.middle_over_edges_c": shape_t["middle_over_edges_c"],
              "pressure_from_temperature.middle_under_edges_c": shape_t["middle_under_edges_c"]}
        if lower and raise_:
            flags.append(Flag(
                rule="PRESSURE_CONFLICT", category="pressure", severity="low",
                title=f"{name.capitalize()}: pressure signals disagree",
                detail=shape_text + pressure_text + " The two point in opposite directions.",
                action=f"Keep the {name} cold pressure as it is for now, and check the hot target for this tyre with your tyre supplier.",
                tyres=[c], evidence=ev, thresholds=th, magnitude=abs(miss or 0)))
            continue
        direction = -1 if lower else 1
        agrees = miss is not None and (miss > tol if lower else miss < -tol)
        change = abs(miss) if agrees else pc["default_change_psi"]
        new_cold = round(cold + direction * change, 1) if cold else None
        rule = "PRESSURE_HIGH" if shape == "over" else "PRESSURE_LOW" if shape == "under" else "PRESSURE_TARGET"
        title = {"PRESSURE_HIGH": f"{name.capitalize()}: pressure too high",
                 "PRESSURE_LOW": f"{name.capitalize()}: pressure too low",
                 "PRESSURE_TARGET": f"{name.capitalize()}: hot pressure {'above' if lower else 'below'} the {target} psi target"}[rule]
        frag = f"the {name} ran {first} psi on the first timed lap and {hot} psi hot" if hot is not None else f"the {name} has no pressure reading"
        if shape in ("over", "under"):
            frag += f", with its centre {abs(mme)} °C {'hotter' if shape == 'over' else 'cooler'} than its edges"
        flags.append(Flag(
            rule=rule, category="pressure", severity="medium", title=title,
            detail=(shape_text + pressure_text).strip(),
            action=f"{'Lower' if lower else 'Raise'} the {name} cold pressure by about {change} psi"
                   + (f", from {cold} to {new_cold} psi." if new_cold else "."),
            tyres=[c], evidence={**ev, "change_psi": round(direction * change, 1), "recommended_cold_psi": new_cold},
            thresholds=th, magnitude=change * 10,
            merge={"key": f"{rule}:{direction}",
                   "title": {"PRESSURE_HIGH": "pressures too high", "PRESSURE_LOW": "pressures too low",
                             "PRESSURE_TARGET": f"hot pressures {'above' if lower else 'below'} the {target} psi target"}[rule],
                   "pre": {"PRESSURE_HIGH": "Both tread centres ran hotter than their edges, the shape of over-inflated tyres.",
                           "PRESSURE_LOW": "Both tread centres ran cooler than their edges, the shape of under-inflated tyres.",
                           "PRESSURE_TARGET": ""}[rule],
                   "frag": frag,
                   "post": f"The hot target is {target} psi ({source}).",
                   "act_all": f"{'Lower' if lower else 'Raise'} the {{axle}} cold pressures: {{parts}}.",
                   "act": f"{name} by about {change} psi" + (f" ({cold} → {new_cold} psi)" if new_cold else "")}))

    build = {c: st["tyres"][c]["pressure_psi"] for c in CORNERS if st["tyres"][c].get("pressure_psi")}
    build = {c: v for c, v in build.items() if v.get("first_lap") is not None and v.get("hot") is not None}
    if build:
        ev = {c: {"first_lap_psi": v["first_lap"], "hot_psi": v["hot"], "rise_psi": round(v["hot"] - v["first_lap"], 1)}
              for c, v in build.items()}
        for c in ev:
            if _cold_set(ctx, c):
                ev[c]["cold_set_psi"] = _cold_set(ctx, c)
        flags.append(Flag(
            rule="PRESSURE_BUILD", category="pressure", severity="info",
            title="Pressure build-up during the session",
            detail="First timed lap to flying laps: " + "; ".join(
                f"{NAMES[c]} {e['first_lap_psi']} → {e['hot_psi']} psi" for c, e in ev.items()) + ".",
            action=None, tyres=list(ev), evidence=ev, thresholds={}))

    for axle, (a, b) in (("front", FRONT), ("rear", REAR)):
        pa, pb = (st["tyres"][a].get("pressure_psi") or {}).get("hot"), (st["tyres"][b].get("pressure_psi") or {}).get("hot")
        if pa is None or pb is None:
            continue
        split = round(pa - pb, 1)
        if abs(split) > pc["axle_split_psi"]:
            high, low = (a, b) if split > 0 else (b, a)
            flags.append(Flag(
                rule="PRESSURE_AXLE_SPLIT", category="pressure", severity="medium",
                title=f"{axle.capitalize()} pressures uneven left to right",
                detail=f"When hot, the {NAMES[high]} ran {max(pa, pb)} psi against {min(pa, pb)} psi on the {NAMES[low]}, "
                       f"a {abs(split)} psi split.",
                action=f"Set the {axle} cold pressures equal, and check the {NAMES[high]} and {NAMES[low]} for a slow leak.",
                tyres=[a, b], evidence={f"{a}_hot_psi": pa, f"{b}_hot_psi": pb, "split_psi": split},
                thresholds={"pressure.axle_split_psi": pc["axle_split_psi"]}, magnitude=abs(split)))
    return flags


def balance_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    b = cfg["balance"]
    ax = st["axle"]
    flags = []
    fr = ax.get("front_minus_rear_c")
    drivetrain = (ctx.get("drivetrain") or "").upper()
    if fr is not None:
        rear_margin = 4 if drivetrain == "RWD" else 0
        front_margin = 4 if drivetrain == "FWD" else 0
        ev = {"front_avg_c": ax["front_avg_c"], "rear_avg_c": ax["rear_avg_c"], "front_minus_rear_c": fr, "drivetrain": drivetrain or None}
        th = {"balance.front_rear_diff_c": b["front_rear_diff_c"]}
        if fr > b["front_rear_diff_c"] + front_margin:
            flags.append(Flag(
                rule="BALANCE_FRONT_HOT", category="balance", severity="low",
                title="Front tyres working harder than the rears",
                detail=f"Fronts averaged {ax['front_avg_c']} °C against {ax['rear_avg_c']} °C at the rear, which usually goes with understeer.",
                action="If the car feels like it pushes wide in corners, look at front grip (camber, pressure) before changing driving style.",
                evidence=ev, thresholds=th, magnitude=fr))
        elif -fr > b["front_rear_diff_c"] + rear_margin:
            flags.append(Flag(
                rule="BALANCE_REAR_HOT", category="balance", severity="low",
                title="Rear tyres working harder than the fronts",
                detail=f"Rears averaged {ax['rear_avg_c']} °C against {ax['front_avg_c']} °C at the front, which usually goes with oversteer or wheelspin on exit.",
                action="Smoother throttle on corner exit will reduce rear heat; if the rear feels loose, review rear pressure and camber.",
                evidence=ev, thresholds=th, magnitude=-fr))
    lr = ax.get("left_minus_right_c")
    if lr is not None and abs(lr) > b["left_right_diff_c"]:
        d = st["driving"]
        hotter = "left" if lr > 0 else "right"
        flags.append(Flag(
            rule="BALANCE_SIDE", category="balance", severity="info",
            title=f"{hotter.capitalize()}-side tyres ran hotter",
            detail=f"The {hotter} side averaged {abs(lr)} °C hotter. Right-hand corners made up "
                   f"{round((d['right_corner_share'] or 0) * 100)}% of moving time and left-hand corners "
                   f"{round((d['left_corner_share'] or 0) * 100)}%, so this is mostly the track layout rather than setup.",
            action=None,
            evidence={"left_minus_right_c": lr, "right_corner_share": d["right_corner_share"], "left_corner_share": d["left_corner_share"]},
            thresholds={"balance.left_right_diff_c": b["left_right_diff_c"]}))
    return flags


def trend_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    tr = cfg["trend"]
    flags = []
    changes = {c: round(st["tyres"][c]["last_third_avg_c"] - st["tyres"][c]["first_third_avg_c"], 1)
               for c in CORNERS if st["tyres"][c].get("first_third_avg_c") is not None}
    if changes:
        avg = sum(changes.values()) / len(changes)
        if abs(avg) > tr["temp_change_c"]:
            rising = avg > 0
            flags.append(Flag(
                rule="TREND_HEATING" if rising else "TREND_COOLING", category="trend", severity="info",
                title="Tyres kept heating up through the session" if rising else "Tyres cooled down through the session",
                detail=f"Average tyre temperature changed by {round(avg, 1)} °C between the first and last third of on-track running.",
                action=None,
                evidence={c: {"first_third_avg_c": st["tyres"][c]["first_third_avg_c"], "last_third_avg_c": st["tyres"][c]["last_third_avg_c"],
                              "change_c": v} for c, v in changes.items()},
                thresholds={"trend.temp_change_c": tr["temp_change_c"]}))

    ls = st["lap_summary"]
    if ls["valid"]:
        lap = ls["first_lap_all_tyres_in_window"]
        flags.append(Flag(
            rule="WARMUP", category="trend", severity="info",
            title=f"All four tyres reached the working window by lap {lap}" if lap else "The tyres never all reached the working window together",
            detail=(f"From lap {lap} every tyre averaged at least {cfg['temperature_window']['low_c']} °C." if lap else
                    f"No lap had all four tyres averaging {cfg['temperature_window']['low_c']} °C or more."),
            action=None,
            evidence={"first_lap_all_tyres_in_window": lap, "valid_laps": ls["valid"]},
            thresholds={"temperature_window.low_c": cfg["temperature_window"]["low_c"]}))
    if ls.get("std_time_s") is not None and ls["std_time_s"] > tr["lap_time_std_s"]:
        flags.append(Flag(
            rule="DRIVER_CONSISTENCY", category="driver", severity="low",
            title="Lap times varied a lot",
            detail=f"Flying laps (excluding warm-up and slow laps) had a spread (standard deviation) of {ls['std_time_s']} s around a median of {ls['median_time_s']} s. "
                   "Large spread usually points to driving or traffic rather than tyre setup, so judge setup changes on your most consistent laps.",
            action="Aim for a run of consistent laps before and after each setup change so the effect is measurable.",
            evidence={"std_time_s": ls["std_time_s"], "median_time_s": ls["median_time_s"], "clean_laps": ls["clean"]},
            thresholds={"trend.lap_time_std_s": tr["lap_time_std_s"]}, magnitude=ls["std_time_s"]))
    cost = ls.get("warmup_median_slower_s")
    if cost is not None and cost > tr["warmup_cost_s"]:
        flags.append(Flag(
            rule="WARMUP_COST", category="driver", severity="info",
            title=f"Warm-up laps were {cost} s slower than flying laps",
            detail=f"The first {cfg['trend']['warmup_laps_per_stint']} laps of each run were a median {cost} s slower than your flying laps. "
                   "That gap is mostly the tyres coming up to temperature, not your driving, so don't judge your pace on those laps.",
            action=None,
            evidence={"warmup_median_slower_s": cost, "warmup_laps": ls["warmup"], "flying_laps": ls["clean"]},
            thresholds={"trend.warmup_cost_s": tr["warmup_cost_s"], "trend.warmup_laps_per_stint": cfg["trend"]["warmup_laps_per_stint"]},
            magnitude=cost))
    bb, tb = ls.get("best_lap_braking_g"), ls.get("typical_braking_g")
    bc, tc = ls.get("best_lap_cornering_g"), ls.get("typical_cornering_g")
    gap = cfg["driver"]["grip_gap_g"]
    if None not in (bb, tb, bc, tc) and (bb - tb > gap or bc - tc > gap):
        more = [w for w, d in (("braking", bb - tb), ("cornering", bc - tc)) if d > gap]
        flags.append(Flag(
            rule="DRIVER_GRIP_USE", category="driver", severity="low",
            title=f"Your best lap used more grip in {' and '.join(more)}",
            detail=f"On your best lap you braked at up to {bb} g and cornered at up to {bc} g; on a typical flying lap it was "
                   f"{tb} g and {tc} g. The car and tyres can take that load, so some lap time is in how hard you use them.",
            action=f"On your next run, aim to repeat your best-lap {' and '.join(more)} effort consistently, one corner at a time.",
            evidence={"best_lap_braking_g": bb, "typical_braking_g": tb, "best_lap_cornering_g": bc, "typical_cornering_g": tc},
            thresholds={"driver.grip_gap_g": gap}, magnitude=max(bb - tb, bc - tc) * 10))
    flags += driver_style_rules(st, cfg, ls)
    if ls.get("best_lap"):
        flags.append(Flag(
            rule="BEST_LAP", category="driver", severity="info",
            title=f"Best lap: lap {ls['best_lap']} ({_fmt_lap(ls['best_time_s'])})",
            detail="Tyre averages on that lap: " + ", ".join(
                f"{NAMES[c]} {v} °C" for c, v in (ls["best_lap_tyre_avg_c"] or {}).items() if v is not None) + ".",
            action=None,
            evidence={"best_lap": ls["best_lap"], "best_time_s": ls["best_time_s"], "tyre_avg_c": ls["best_lap_tyre_avg_c"]},
            thresholds={}))
    return flags


def driver_style_rules(st: dict, cfg: dict, ls: dict) -> list[Flag]:
    dr = cfg["driver"]
    m = {x["key"]: x for x in st.get("driver_style", {}).get("metrics", [])}
    lap = ls.get("best_lap")
    notes, actions, ev = [], [], {}

    def pair(key):
        x = m.get(key) or {}
        return x.get("best"), x.get("typical")

    b, t = pair("full_throttle_pct")
    if None not in (b, t) and b - t >= dr["style_gap_throttle_pct"]:
        notes.append(f"you were at full throttle for {b}% of the lap against {t}% on a typical lap")
        actions.append(f"get back to full throttle earlier on corner exits, as on lap {lap}")
        ev["full_throttle_pct"] = {"best": b, "typical": t}
    b, t = pair("coasting_pct")
    coasting_noted = False
    if None not in (b, t) and t - b >= dr["style_gap_coasting_pct"]:
        notes.append(f"you coasted for {b}% of the lap against {t}% on a typical lap")
        actions.append("go straight from brake to throttle with less coasting")
        ev["coasting_pct"] = {"best": b, "typical": t}
        coasting_noted = True
    b, t = pair("trail_braking_pct")
    if None not in (b, t) and abs(b - t) >= dr["style_gap_trail_pct"]:
        more = b > t
        notes.append(f"you were still braking while turning for {b}% of your braking against {t}% on a typical lap")
        actions.append("carry a little more brake into the turn-in" if more else "finish more of your braking in a straight line before turning")
        ev["trail_braking_pct"] = {"best": b, "typical": t}
    flags = []
    if notes and lap:
        flags.append(Flag(
            rule="DRIVER_BEST_LAP_STYLE", category="driver", severity="low",
            title=f"What was different on your best lap (lap {lap})",
            detail="On your best lap " + "; ".join(notes) + ".",
            action=actions[0][0].upper() + actions[0][1:] + ".",
            evidence={**ev, "best_lap": lap},
            thresholds={k: dr[k] for k in ("style_gap_throttle_pct", "style_gap_coasting_pct", "style_gap_trail_pct")},
            magnitude=len(notes)))
    b, t = pair("coasting_pct")
    if t is not None and t > dr["coasting_max_pct"] and not coasting_noted:
        flags.append(Flag(
            rule="DRIVER_COASTING", category="driver", severity="low",
            title="Time spent coasting",
            detail=f"On a typical flying lap you were on neither the throttle nor the brake for {t}% of the lap.",
            action="Aim to be either braking or accelerating; shorten the gap between releasing the brake and picking up the throttle.",
            evidence={"typical_coasting_pct": t}, thresholds={"driver.coasting_max_pct": dr["coasting_max_pct"]}, magnitude=t))
    return flags


def data_quality_rules(st: dict, cfg: dict, ctx: dict) -> list[Flag]:
    flags = []
    q = st["data_quality"]
    off = {c: z for c, z in q["off_tread_zones"].items() if z}
    if off:
        flags.append(Flag(
            rule="DATA_SENSOR_ALIGNMENT", category="data", severity="info",
            title="Some sensor zones appear to read off the tread",
            detail="These zones read much colder than the rest of the tyre in a sharp step, so they were left out of the analysis: "
                   + "; ".join(f"{NAMES[c]} zone {', '.join(map(str, z))}" for c, z in off.items())
                   + ". Check the Wheel Turtle sensor aim.",
            action=None, tyres=list(off), evidence=off, thresholds={
                "off_tread.edge_drop_c": cfg["off_tread"]["edge_drop_c"]}))
    missing = [c for c, ok in q["pressure_available"].items() if not ok]
    frozen = q.get("pressure_frozen", [])
    if missing:
        flags.append(Flag(
            rule="DATA_NO_PRESSURE", category="data", severity="info",
            title="No usable TPMS pressure for " + _join(missing),
            detail="Pressure advice for these tyres is based on the temperature profile only."
                   + (f" The {_join(frozen)} sensor reported the same value all session (frozen), so it was ignored."
                      if frozen else ""),
            action=None, tyres=missing, evidence={"missing": missing, "frozen": frozen},
            thresholds={"data.frozen_pressure_mode_share": cfg["data"]["frozen_pressure_mode_share"]} if frozen else {}))
    return flags


RULESETS = (temperature_rules, camber_rules, pressure_rules, balance_rules, trend_rules, data_quality_rules)

SETUP_FIXES = {"CAMBER_ADD", "CAMBER_REDUCE", "CAMBER_STRAIGHT_LOW", "PRESSURE_HIGH", "PRESSURE_LOW", "PRESSURE_TARGET",
               "PRESSURE_AXLE_SPLIT"}


def suspension_hint(flags: list[Flag]) -> list[Flag]:
    out = []
    for f in flags:
        if f.rule not in ("BALANCE_FRONT_HOT", "BALANCE_REAR_HOT"):
            continue
        axle = FRONT if f.rule == "BALANCE_FRONT_HOT" else REAR
        if any(g.rule in SETUP_FIXES and set(g.tyres) & set(axle) for g in flags):
            continue
        front = f.rule == "BALANCE_FRONT_HOT"
        out.append(Flag(
            rule="SUSPENSION_HINT", category="balance", severity="low",
            title="Balance issue not explained by camber or pressure",
            detail=f"The {'front' if front else 'rear'} tyres work harder, but their camber and pressure indicators look right, "
                   "so the imbalance is more likely to come from suspension balance.",
            action=("Consider a softer front anti-roll bar or a stiffer rear one, or a small ride-height change; make one change at a time."
                    if front else
                    "Consider a softer rear anti-roll bar or a stiffer front one, or a small ride-height change; make one change at a time."),
            evidence={**f.evidence, "based_on": f.rule}, thresholds=f.thresholds, magnitude=f.magnitude))
    return out


def merge_axles(flags: list[Flag]) -> list[Flag]:
    out, used = [], set()
    for axle, (a, b) in (("front", FRONT), ("rear", REAR)):
        for f in flags:
            if id(f) in used or not f.merge or f.tyres != [a]:
                continue
            g = next((x for x in flags if id(x) not in used and x.merge.get("key") == f.merge["key"] and x.tyres == [b]), None)
            if g is None:
                continue
            used |= {id(f), id(g)}
            m = f.merge
            frags = f"{m['frag'][0].upper()}{m['frag'][1:]}; {g.merge['frag']}."
            out.append(Flag(
                rule=f.rule, category=f.category, severity=max(f.severity, g.severity, key=list(SEVERITY_ORDER).index),
                title=f"{axle.capitalize()} tyres: {m['title']}",
                detail=" ".join(x for x in (m["pre"], frags, m["post"]) if x),
                action=m["act_all"].format(axle=axle, parts="; ".join(x.merge["act"] for x in (f, g))),
                tyres=[a, b], evidence={a: f.evidence, b: g.evidence}, thresholds=f.thresholds,
                magnitude=max(f.magnitude, g.magnitude)))
    return [f for f in flags if id(f) not in used] + out


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}


def run_rules(stats: dict, cfg: dict, context: dict | None = None) -> list[dict]:
    ctx = context or {}
    flags = merge_axles([f for rs in RULESETS for f in rs(stats, cfg, ctx)])
    flags += suspension_hint(flags)
    weights = cfg["severity_weights"]
    out = [f.to_dict(weights) for f in flags]
    out.sort(key=lambda f: -f["priority"])
    for i, f in enumerate(out, 1):
        f["id"] = f"F{i}"
    return out


CORNER_RULES = {"PRESSURE_HIGH", "PRESSURE_LOW", "PRESSURE_TARGET", "PRESSURE_CONFLICT",
                "CAMBER_ADD", "CAMBER_STRAIGHT_LOW", "CAMBER_REDUCE"}

TOOLS = {
    "pressure": "No tools: tyre gauge and air, about 5 minutes in the pits",
    "camber": "Needs tools: camber gauge and spanners, or an alignment shop",
    "suspension": "Needs tools: anti-roll bar or ride-height adjustment",
    "driving": "No tools: driving technique",
}


def heat_shape(tyre: dict, cfg: dict) -> dict:
    mme = tyre["all"].get("middle_minus_edges")
    cio = tyre.get("corner_loaded", {}).get("inner_minus_outer")
    pt, even = cfg["pressure_from_temperature"], cfg["camber"]["corner_even_tolerance_c"]
    if mme is not None and mme > pt["middle_over_edges_c"]:
        return {"key": "centre_hot", "label": "Hot centre", "meaning": "over-inflated shape"}
    if mme is not None and -mme > pt["middle_under_edges_c"]:
        return {"key": "edges_hot", "label": "Hot edges", "meaning": "under-inflated shape"}
    if cio is not None and cio > even:
        return {"key": "inside_hot", "label": "Hot inside edge in corners", "meaning": "too much negative camber"}
    if cio is not None and -cio > even:
        return {"key": "outside_hot", "label": "Hot outside edge in corners", "meaning": "not enough negative camber"}
    if mme is None:
        return {"key": "unknown", "label": "Not enough data", "meaning": ""}
    return {"key": "even", "label": "Even across the tread", "meaning": ""}


def setup_sheet(stats: dict, flags: list[dict], cfg: dict, ctx: dict) -> dict:
    by_tyre = {c: [f for f in flags if c in f["tyres"] and f["category"] in ("pressure", "camber")] for c in CORNERS}
    corners = {}
    for c in CORNERS:
        mine = {f["rule"]: f for f in by_tyre[c]}
        pf = next((mine[r] for r in ("PRESSURE_HIGH", "PRESSURE_LOW", "PRESSURE_TARGET", "PRESSURE_CONFLICT") if r in mine), None)
        if pf and pf["rule"] != "PRESSURE_CONFLICT":
            ev = pf["evidence"].get(c, pf["evidence"])
            change = ev["change_psi"]
            pressure = {"change_psi": change, "label": f"{'+' if change > 0 else '−'}{abs(change)} psi cold",
                        "to_psi": ev.get("recommended_cold_psi"), "flag": pf["id"], "tools": TOOLS["pressure"]}
        elif pf:
            pressure = {"change_psi": 0, "label": "Hold, check target", "to_psi": None, "flag": pf["id"], "tools": TOOLS["pressure"]}
        else:
            hot = (stats["tyres"][c].get("pressure_psi") or {}).get("hot")
            pressure = {"change_psi": 0, "label": "No change" if hot is not None else "No pressure data", "to_psi": None,
                        "flag": None, "tools": None}
        cf = next((mine[r] for r in ("CAMBER_ADD", "CAMBER_STRAIGHT_LOW", "CAMBER_REDUCE") if r in mine), None)
        if cf:
            more = cf["rule"] != "CAMBER_REDUCE"
            step = "0.25–0.5°" if cf["rule"] != "CAMBER_STRAIGHT_LOW" else "0.25°"
            camber = {"direction": 1 if more else -1, "label": f"{'More' if more else 'Less'} negative, {step}",
                      "flag": cf["id"], "tools": TOOLS["camber"]}
        else:
            camber = {"direction": 0, "label": "No change", "flag": None, "tools": None}
        corners[c] = {"pressure": pressure, "camber": camber, "heat_shape": heat_shape(stats["tyres"][c], cfg)}
    other = []
    for f in flags:
        if not f["action"] or f["rule"] in CORNER_RULES:
            continue
        kind = {"balance": "suspension" if f["rule"] == "SUSPENSION_HINT" else "driving", "driver": "driving",
                "temperature": "driving", "pressure": "pressure", "camber": "camber"}.get(f["category"], "driving")
        other.append({"flag": f["id"], "title": f["title"], "action": f["action"], "tools": TOOLS[kind]})
    target = ctx.get("target_hot_pressure_psi") or cfg["pressure"]["target_hot_psi"]
    return {"corners": corners, "other": other, "target_hot_psi": target,
            "target_source": "entered" if ctx.get("target_hot_pressure_psi") else "default"}


def pick_takeaway(flags: list[dict]) -> dict | None:
    return next((f for f in flags if f["action"] and f["severity"] in ("high", "medium", "low")), None)


def _fmt_lap(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"
