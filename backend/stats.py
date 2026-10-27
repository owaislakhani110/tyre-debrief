from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .ingest import CORNERS, ZONES, Session, zone_col

FRONT, REAR = ("LF", "RF"), ("LR", "RR")
LEFT, RIGHT = ("LF", "LR"), ("RF", "RR")


def _r(x, nd=1):
    if x is None:
        return None
    try:
        if np.isnan(x):
            return None
    except TypeError:
        pass
    return round(float(x), nd)


def _nanmean(a, axis=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.asarray(a, dtype=float), axis=axis)


def clean_temperatures(df: pd.DataFrame, cfg: dict, sample_rate: float) -> dict:
    lo, hi = cfg["data"]["plausible_temp_c"]
    window = max(3, int(round(sample_rate or 20)) | 1)
    report = {}
    for c in CORNERS:
        cols = [zone_col(c, z) for z in range(1, ZONES + 1)]
        block = df[cols]
        total = block.size
        out_of_range = (block < lo) | (block > hi)
        block = block.mask(out_of_range)
        med = block.rolling(window, center=True, min_periods=window // 2).median()
        spikes = (block - med).abs() > cfg["data"]["spike_threshold_c"]
        block = block.mask(spikes)
        df[cols] = block
        report[c] = {
            "dropout_or_out_of_range_share": _r(out_of_range.to_numpy().sum() / total, 3),
            "spikes_removed": int(spikes.to_numpy().sum()),
            "valid_share": _r(block.notna().to_numpy().sum() / total, 3),
        }
    return report


def clean_pressures(df: pd.DataFrame, cfg: dict, already_psi: bool = False) -> tuple[dict, list[str]]:
    scale = 1.0 if already_psi else cfg["data"]["pressure_scale_to_psi"]
    lo, hi = cfg["data"]["plausible_pressure_psi"]
    available, frozen = {}, []
    for c in CORNERS:
        col = f"{c}_pressure"
        if col not in df:
            available[c] = False
            continue
        psi = df[col] * scale
        df[col] = psi.where((psi >= lo) & (psi <= hi))
        ok = bool(df[col].notna().mean() > 0.2)
        if ok and df[col].round(2).value_counts(normalize=True).iloc[0] > cfg["data"]["frozen_pressure_mode_share"]:
            frozen.append(c)
            df[col] = np.nan
            ok = False
        available[c] = ok
    return available, frozen


def detect_off_tread(profile: np.ndarray, cfg: dict) -> list[int]:
    o = cfg["off_tread"]
    if np.isnan(profile).sum() > 2:
        return []
    centre = profile[2:6]
    if np.nanmax(centre) - np.nanmin(centre) > o["max_centre_spread_c"]:
        return []
    ref = np.nanmedian(centre)
    excluded = []
    for edge in (range(0, o["max_zones_per_edge"]), range(ZONES - 1, ZONES - 1 - o["max_zones_per_edge"], -1)):
        for i in edge:
            if np.isnan(profile[i]) or ref - profile[i] >= o["edge_drop_c"]:
                excluded.append(i + 1)
            else:
                break
    return sorted(excluded)


def _orient(profile: np.ndarray, corner: str, cfg: dict) -> np.ndarray:
    return profile if cfg["zone_orientation"].get(corner, "inner") == "inner" else profile[::-1]


def edge_summary(profile_io: np.ndarray) -> dict:
    idx = np.where(~np.isnan(profile_io))[0]
    if len(idx) < 4:
        return {"inner": None, "middle": None, "outer": None, "inner_minus_outer": None, "middle_minus_edges": None}
    inner = np.mean(profile_io[idx[:2]])
    outer = np.mean(profile_io[idx[-2:]])
    mid_idx = idx[2:-2] if len(idx) > 4 else idx[1:-1]
    middle = np.mean(profile_io[mid_idx])
    return {
        "inner": _r(inner), "middle": _r(middle), "outer": _r(outer),
        "inner_minus_outer": _r(inner - outer),
        "middle_minus_edges": _r(middle - (inner + outer) / 2),
    }


def _held_max(values: np.ndarray, mask: np.ndarray, n: int):
    """Highest value sustained for n consecutive samples inside mask."""
    arr = np.where(mask[:, None] if values.ndim == 2 else mask, values, np.nan)
    rolled = pd.DataFrame(arr).rolling(n, min_periods=n).mean().to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out = np.nanmax(rolled, axis=0)
    return out if values.ndim == 2 else out[0]


def lap_table(session: Session, cfg: dict) -> list[dict]:
    m = session.lap_markers
    duration = session.meta["duration_s"]
    if len(m) < 2:
        return []
    pairs = list(zip(m[:-1], m[1:]))
    if duration and abs(m[-1] - duration) < 0.5:
        pairs = pairs[:-1]
    laps = [{"lap": i + 1, "start_s": a, "end_s": b, "time_s": round(b - a, 3)} for i, (a, b) in enumerate(pairs)]
    if not laps:
        return []
    median = float(np.median([l["time_s"] for l in laps]))
    for l in laps:
        l["valid"] = l["time_s"] >= cfg["data"]["min_lap_fraction_of_median"] * median
    valid = [l for l in laps if l["valid"]]
    best = min((l["time_s"] for l in valid), default=None)
    stint_lap = 0
    for l in laps:
        l["slow"] = bool(best and l["valid"] and l["time_s"] > best * 1.15)
        stint_lap = 0 if (l["slow"] or not l["valid"]) else stint_lap + 1
        l["stint_lap"] = stint_lap
        l["warmup"] = 0 < stint_lap <= cfg["trend"]["warmup_laps_per_stint"]
        l["flying"] = l["valid"] and not l["slow"] and not l["warmup"]
    return laps


def compute_stats(session: Session, cfg: dict) -> dict:
    df = session.data.copy()
    sr = session.meta.get("sample_rate_hz") or 20
    quality = {"temperature": clean_temperatures(df, cfg, sr)}
    pressure_ok, frozen = clean_pressures(df, cfg, session.meta.get("pressure_in_psi", False))
    quality["pressure_available"] = pressure_ok
    quality["pressure_frozen"] = frozen

    speed = df["speed"] if "speed" in df else pd.Series(np.full(len(df), 100.0))
    on_track = (speed >= cfg["data"]["min_speed_kmh"]).to_numpy()
    if on_track.sum() < 200:
        on_track = np.ones(len(df), dtype=bool)
        quality.setdefault("notes", []).append("No GPS speed while moving; analysed the whole file.")

    ds = cfg["driving_state"]
    # Positive lateral g is a right-hand turn.
    lat_signed = df["lat_g"].to_numpy() if "lat_g" in df else np.zeros(len(df))
    lat = np.abs(lat_signed)
    fast = speed.to_numpy() >= ds["min_speed_kmh"]
    lon = df["lon_g"].to_numpy() if "lon_g" in df else None
    steady = np.abs(lon) < ds["straight_max_lon_g"] if lon is not None else np.ones(len(df), dtype=bool)
    straight = fast & (lat < ds["straight_max_lat_g"]) & steady
    right_turn = fast & (lat_signed > ds["corner_min_lat_g"])
    left_turn = fast & (lat_signed < -ds["corner_min_lat_g"])
    loaded = {"LF": right_turn, "LR": right_turn, "RF": left_turn, "RR": left_turn}

    lo, hi = cfg["temperature_window"]["low_c"], cfg["temperature_window"]["high_c"]
    laps = lap_table(session, cfg)
    t = df["time"].to_numpy()
    flying_laps = [l for l in laps if l["flying"]]
    if len(flying_laps) >= cfg["trend"]["min_flying_laps"]:
        window_mask = np.zeros(len(df), dtype=bool)
        for l in flying_laps:
            window_mask |= (t >= l["start_s"]) & (t < l["end_s"])
        window_mask &= on_track
        window_basis = f"{len(flying_laps)} flying laps"
    else:
        window_mask, window_basis = on_track, "all on-track running"

    hold = max(1, int(round(cfg["temperature_window"]["peak_hold_s"] * sr)))
    views_masks = {"all": window_mask, "straight": straight & window_mask}

    def window_stats(series: np.ndarray, mask: np.ndarray) -> dict:
        v = series[mask]
        v = v[~np.isnan(v)]
        if v.size < 40:
            return {"average_c": None, "peak_c": None, "share_in_window": None, "share_below_window": None,
                    "share_above_window": None, "low_c": None}
        return {
            "average_c": _r(np.mean(v)), "peak_c": _r(_held_max(series, mask, hold)), "low_c": _r(np.percentile(v, 5)),
            "share_in_window": _r(np.mean((v >= lo) & (v <= hi)), 3),
            "share_below_window": _r(np.mean(v < lo), 3), "share_above_window": _r(np.mean(v > hi), 3),
        }

    tyres, off_tread = {}, {}
    for c in CORNERS:
        z = df[[zone_col(c, k) for k in range(1, ZONES + 1)]].to_numpy(dtype=float)
        zt = z[on_track]
        raw_profile = _nanmean(zt, axis=0)
        excl = detect_off_tread(raw_profile, cfg)
        off_tread[c] = excl
        keep = np.array([k + 1 not in excl for k in range(ZONES)])
        z_valid = np.where(keep, z, np.nan)
        tyre_mean = _nanmean(z_valid, axis=1)
        tm = tyre_mean[on_track]
        tm_ok = tm[~np.isnan(tm)]
        views = {}
        for name, mask in {**views_masks, "corner": loaded[c] & window_mask}.items():
            n = int(mask.sum())
            if n < 40:
                views[name] = {"samples": n, "profile": None, "zone_peaks": None}
                continue
            prof = _orient(_nanmean(z_valid[mask], axis=0), c, cfg)
            zone_peaks = _orient(_held_max(z_valid, mask, hold), c, cfg)
            views[name] = {**window_stats(tyre_mean, mask), **edge_summary(prof), "samples": n,
                           "profile": [_r(v) for v in prof], "zone_peaks": [_r(v) for v in zone_peaks]}
        if views["all"]["profile"] is None:
            views["all"]["profile"] = [_r(v) for v in _orient(np.where(keep, raw_profile, np.nan), c, cfg)]

        entry = {
            "session_average_c": _r(np.mean(tm_ok)) if tm_ok.size else None,
            **{k: views["all"].get(k) for k in ("average_c", "peak_c", "low_c", "share_in_window",
                                                 "share_below_window", "share_above_window")},
            "corner_peak_c": views["corner"].get("peak_c"),
            "profile_inside_to_outside": views["all"]["profile"],
            "excluded_zones": excl,
            "all": edge_summary(np.array(views["all"]["profile"], dtype=float)),
            "straight": {**{k: views["straight"].get(k) for k in ("inner", "middle", "outer", "inner_minus_outer",
                                                                  "middle_minus_edges")}, "samples": views["straight"]["samples"]},
            "corner_loaded": {**{k: views["corner"].get(k) for k in ("inner", "middle", "outer", "inner_minus_outer",
                                                                     "middle_minus_edges")}, "samples": views["corner"]["samples"]},
            "profile_straight": views["straight"]["profile"],
            "profile_corner_loaded": views["corner"]["profile"],
            "views": views,
        }
        thirds = np.array_split(tm_ok, 3) if tm_ok.size >= 30 else None
        entry["first_third_avg_c"] = _r(np.mean(thirds[0])) if thirds else None
        entry["last_third_avg_c"] = _r(np.mean(thirds[2])) if thirds else None

        if pressure_ok.get(c):
            pr = df[f"{c}_pressure"].to_numpy()
            ok = ~np.isnan(pr)
            first = next((l for l in laps if l["valid"]), None)
            first_lap = pr[ok & (t >= first["start_s"]) & (t < first["end_s"])] if first else np.array([])
            hot = pr[ok & window_mask]
            run = pr[ok & on_track]
            thirds_p = np.array_split(run, 3) if run.size >= 30 else None
            entry["pressure_psi"] = {
                "first_lap": _r(np.median(first_lap)) if first_lap.size else None,
                "hot": _r(np.median(hot)) if hot.size else (_r(np.median(run)) if run.size else None),
                "max": _r(np.percentile(run, 98)) if run.size else None,
                "end": _r(np.median(thirds_p[2])) if thirds_p else None,
            }
        else:
            entry["pressure_psi"] = None
        if f"{c}_tpms_temp" in df:
            tt = df[f"{c}_tpms_temp"].to_numpy()[on_track]
            tt = tt[(tt > 0) & (tt < 150)]
            entry["tpms_air_temp_c"] = _r(np.median(tt)) if tt.size else None

        for lap in laps:
            m = (t >= lap["start_s"]) & (t < lap["end_s"]) & on_track
            v = tyre_mean[m]
            v = v[~np.isnan(v)]
            lap.setdefault("tyre_avg_c", {})[c] = _r(np.mean(v)) if v.size else None
            if pressure_ok.get(c):
                pv = df[f"{c}_pressure"].to_numpy()[m]
                pv = pv[~np.isnan(pv)]
                lap.setdefault("pressure_psi", {})[c] = _r(np.median(pv)) if pv.size else None
        tyres[c] = entry

    quality["off_tread_zones"] = off_tread

    def group(cs):
        vals = [tyres[c]["average_c"] for c in cs if tyres[c]["average_c"] is not None]
        return float(np.mean(vals)) if vals else None

    f, r_, l, rt = group(FRONT), group(REAR), group(LEFT), group(RIGHT)
    axle = {
        "front_avg_c": _r(f), "rear_avg_c": _r(r_), "left_avg_c": _r(l), "right_avg_c": _r(rt),
        "front_minus_rear_c": _r(f - r_) if f is not None and r_ is not None else None,
        "left_minus_right_c": _r(l - rt) if l is not None and rt is not None else None,
    }

    dr = cfg["driver"]
    throttle = df["throttle"].to_numpy() if "throttle" in df else None
    if "brake_pressure" in df and np.nanpercentile(df["brake_pressure"], 99) > 0:
        bp = df["brake_pressure"].to_numpy()
        braking = bp > dr["brake_on_fraction"] * np.nanpercentile(bp, 99)
    elif lon is not None:
        braking = lon < -dr["brake_on_g"]
    else:
        braking = None
    for lap in laps:
        m = (t >= lap["start_s"]) & (t < lap["end_s"])
        mf = m & fast
        mv = m & on_track
        lap["braking_g"] = _r(np.nanpercentile(-lon[mf], 98), 2) if lon is not None and mf.sum() > 40 else None
        lap["cornering_g"] = _r(np.nanpercentile(lat[mf], 98), 2) if mf.sum() > 40 else None
        if mv.sum() > 40:
            if throttle is not None:
                lap["full_throttle_pct"] = _r(np.mean(throttle[mv] > dr["full_throttle_pct"]) * 100)
                if braking is not None:
                    lap["coasting_pct"] = _r(np.mean(~braking[mv] & (throttle[mv] < dr["coast_throttle_pct"])) * 100)
            if braking is not None and (m & braking).sum() > 20:
                lap["trail_braking_pct"] = _r(np.mean(lat[m & braking] > dr["trail_lat_g"]) * 100)

    moving = fast.sum() or 1
    driving = {
        "straight_share": _r(straight.sum() / moving, 3),
        "right_corner_share": _r(right_turn.sum() / moving, 3),
        "left_corner_share": _r(left_turn.sum() / moving, 3),
        "max_lateral_g": _r(np.nanpercentile(lat[fast], 99), 2) if fast.any() else None,
    }

    valid = [l for l in laps if l["valid"]]
    clean_laps = flying_laps
    warmup_laps = [l for l in laps if l["warmup"]]
    warmup_cost = None
    if warmup_laps and len(clean_laps) >= 2:
        warmup_cost = float(np.median([l["time_s"] for l in warmup_laps]) - np.median([l["time_s"] for l in clean_laps]))
    first_in_window = None
    for l in valid:
        temps = [l["tyre_avg_c"].get(c) for c in CORNERS]
        if all(v is not None and v >= lo for v in temps):
            first_in_window = l["lap"]
            break
    best = min(valid, key=lambda l: l["time_s"]) if valid else None
    lap_summary = {
        "count": len(laps), "valid": len(valid), "clean": len(clean_laps), "warmup": len(warmup_laps),
        "window_basis": window_basis,
        "warmup_median_slower_s": _r(warmup_cost, 2),
        "best_lap": best["lap"] if best else None,
        "best_time_s": best["time_s"] if best else None,
        "median_time_s": _r(np.median([l["time_s"] for l in clean_laps]), 3) if clean_laps else None,
        "std_time_s": _r(np.std([l["time_s"] for l in clean_laps]), 2) if len(clean_laps) >= 3 else None,
        "first_lap_all_tyres_in_window": first_in_window,
        "best_lap_tyre_avg_c": best["tyre_avg_c"] if best else None,
        "best_lap_braking_g": best.get("braking_g") if best else None,
        "best_lap_cornering_g": best.get("cornering_g") if best else None,
        "typical_braking_g": _median_of(clean_laps, "braking_g"),
        "typical_cornering_g": _median_of(clean_laps, "cornering_g"),
    }
    style_keys = (("full_throttle_pct", "Full throttle", "% of lap"), ("coasting_pct", "Coasting (no throttle or brake)", "% of lap"),
                  ("trail_braking_pct", "Braking while turning (trail braking)", "% of braking"),
                  ("braking_g", "Peak braking", "g"), ("cornering_g", "Peak cornering", "g"))
    driver_style = {
        "inputs": "throttle and brake channels" if throttle is not None and "brake_pressure" in df else "G-force only",
        "metrics": [{"key": k, "label": label, "unit": unit, "best": best.get(k) if best else None,
                     "typical": _median_of(clean_laps, k, 1 if unit.startswith("%") else 2)} for k, label, unit in style_keys],
    }

    ambient = None
    if "ambient" in df:
        a = df["ambient"].to_numpy()
        a = a[(a > -20) & (a < 60)]
        ambient = _r(np.median(a)) if a.size else None

    s = session.meta
    return {
        "session": {
            "racer": s.get("racer"), "vehicle": s.get("vehicle"), "track": s.get("session"),
            "date": s.get("date"), "start_time": s.get("start_time"),
            "duration_s": _r(s.get("duration_s"), 0), "on_track_share": _r(on_track.mean(), 3),
            "ambient_c": ambient, "filename": s.get("filename"),
        },
        "data_quality": quality,
        "tyres": tyres,
        "axle": axle,
        "driving": driving,
        "laps": laps,
        "lap_summary": lap_summary,
        "driver_style": driver_style,
    }


def _median_of(laps: list[dict], key: str, nd: int = 2):
    vals = [l[key] for l in laps if l.get(key) is not None]
    return _r(np.median(vals), nd) if len(vals) >= 2 else None
