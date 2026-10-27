from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import yaml

from .ingest import CORNERS, ZONES, IngestError, parse_session, zone_col
from .narrative import configured_providers, generate_debrief, template_narrative
from .rules import pick_takeaway, run_rules, setup_sheet
from .stats import compute_stats

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"

CONTEXT_FIELDS = ("make", "model", "drivetrain", "tyre_compound", "camber_front_deg", "camber_rear_deg",
                  "cold_pressure_front_psi", "cold_pressure_rear_psi", "target_hot_pressure_psi", "session_type", "notes")


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def clean_context(raw: dict | None) -> dict:
    ctx = {}
    for k in CONTEXT_FIELDS:
        v = (raw or {}).get(k)
        if v is None or str(v).strip() == "":
            continue
        v = str(v).strip()[:200]
        if k.endswith(("_deg", "_psi")):
            try:
                v = float(v)
            except ValueError:
                raise IngestError(f"'{k.replace('_', ' ')}' must be a number.")
        ctx[k] = v
    return ctx


def session_problem(session, cfg: dict) -> str | None:
    df = session.data
    lo, hi = cfg["data"]["plausible_temp_c"]
    zones = df[[zone_col(c, z) for c in CORNERS for z in range(1, ZONES + 1)]].to_numpy(dtype=float)
    valid = (zones >= lo) & (zones <= hi)
    moving = np.ones(len(df), dtype=bool)
    if "speed" in df:
        moving = (df["speed"] >= cfg["data"]["min_speed_kmh"]).to_numpy()
        rate = session.meta.get("sample_rate_hz") or 20
        if moving.sum() < cfg["data"]["min_running_s"] * rate:
            return (f"This recording has no real track running (top speed {df['speed'].max():.0f} km/h), so there is nothing "
                    "to analyse. It looks like a paddock or pit-lane recording; upload a session with laps on track.")
    if valid[moving].mean() >= cfg["data"]["min_valid_temp_share"]:
        return None
    if not valid.any():
        return ("This session has no tyre-temperature data: every Wheel Turtle reading in the file is zero or empty. "
                "Check the sensors were paired with the logger and logging before going out.")
    return ("This session has no tyre-temperature data while driving: the Wheel Turtle sensors only reported while the car "
            "was stopped. Check the sensors stay connected on track (battery, Bluetooth range, logger pairing).")


def analyse(source, filename: str = "", context: dict | None = None, cfg: dict | None = None,
            with_narrative: bool | str = True) -> dict:
    cfg = cfg or load_config()
    ctx = clean_context(context)
    timings = {}
    t0 = time.perf_counter()
    session = parse_session(source, filename)
    timings["parse_s"] = round(time.perf_counter() - t0, 2)
    problem = session_problem(session, cfg)
    if problem:
        raise IngestError(problem)

    t1 = time.perf_counter()
    stats = compute_stats(session, cfg)
    timings["stats_s"] = round(time.perf_counter() - t1, 2)

    t2 = time.perf_counter()
    flags = run_rules(stats, cfg, ctx)
    takeaway = pick_takeaway(flags)
    sheet = setup_sheet(stats, flags, cfg, ctx)
    timings["rules_s"] = round(time.perf_counter() - t2, 3)

    narrative = None
    if with_narrative == "deferred":
        narrative = template_narrative(stats, flags, takeaway, pending=bool(configured_providers()))
    elif with_narrative:
        t3 = time.perf_counter()
        narrative = generate_debrief(stats, flags, takeaway, ctx)
        timings["narrative_s"] = round(time.perf_counter() - t3, 2)
    timings["total_s"] = round(time.perf_counter() - t0, 2)

    return {
        "context": ctx,
        "stats": stats,
        "flags": flags,
        "takeaway_flag_id": takeaway["id"] if takeaway else None,
        "setup_sheet": sheet,
        "narrative": narrative,
        "timings": timings,
        "config_window": cfg["temperature_window"],
    }


def complete_narrative(report: dict) -> dict:
    takeaway = next((f for f in report["flags"] if f["id"] == report.get("takeaway_flag_id")), None)
    t0 = time.perf_counter()
    narrative = generate_debrief(report["stats"], report["flags"], takeaway, report.get("context") or {})
    return {**narrative, "seconds": round(time.perf_counter() - t0, 2)}
