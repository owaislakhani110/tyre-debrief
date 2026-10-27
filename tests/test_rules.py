from backend.ingest import parse_session
from backend.pipeline import load_config
from backend.rules import pick_takeaway, run_rules
from backend.stats import compute_stats

from .synth import CORNERS, make_csv

CFG = load_config()


def flags_for(context=None, **kw):
    st = compute_stats(parse_session(make_csv(**kw).encode(), "t.csv"), CFG)
    return run_rules(st, CFG, context or {})


def rules(flags, tyre=None):
    return {f["rule"] for f in flags if tyre is None or tyre in f["tyres"]}


def tyre_flag(flags, rule, tyre):
    f = next(f for f in flags if f["rule"] == rule and tyre in f["tyres"])
    return f, f["evidence"].get(tyre, f["evidence"])


def test_outer_edge_hot_in_corners_means_add_camber():
    straight = {c: [72] * 8 for c in CORNERS}
    corner = {c: [66, 68, 70, 72, 74, 76, 78, 80] for c in CORNERS}
    flags = flags_for(profiles=straight, corner_profiles=corner)
    for c in CORNERS:
        assert "CAMBER_ADD" in rules(flags, c)
    f = next(f for f in flags if f["rule"] == "CAMBER_ADD")
    assert f["severity"] == "high"
    assert "camber.corner_even_tolerance_c" in f["thresholds"]


def test_inside_edge_hot_in_corners_means_reduce_camber():
    straight = {c: [90, 87, 84, 81, 78, 75, 72, 69] for c in CORNERS}
    corner = {c: [85, 83, 81, 79, 77, 75, 73, 71] for c in CORNERS}
    flags = flags_for(profiles=straight, corner_profiles=corner)
    assert "CAMBER_REDUCE" in rules(flags, "LF")


def test_even_corners_and_warm_inside_on_straights_is_ok():
    flags = flags_for(profiles={c: [84, 81, 78, 75, 72, 69, 66, 63] for c in CORNERS}, corner_profiles={c: [72] * 8 for c in CORNERS})
    assert "CAMBER_OK" in rules(flags, "LF")


def test_flat_tyre_on_straights_gives_camber_tell():
    flags = flags_for(profiles={c: [70] * 8 for c in CORNERS})
    f, _ = tyre_flag(flags, "CAMBER_STRAIGHT_LOW", "LF")
    assert "15 °C" in f["detail"] and "negative camber" in f["action"]
    assert f["tyres"] == ["LF", "RF"] and f["title"].startswith("Front tyres")
    assert "CAMBER_OK" not in rules(flags, "LF")


def test_hot_centre_means_pressure_high():
    prof = {c: [64, 66, 74, 76, 76, 74, 66, 64] for c in CORNERS}
    flags = flags_for(profiles=prof)
    assert "PRESSURE_HIGH" in rules(flags, "RR")


def test_cool_centre_means_pressure_low():
    prof = {c: [76, 74, 66, 64, 64, 66, 74, 76] for c in CORNERS}
    flags = flags_for(profiles=prof, pressure_psi=30)
    _, ev = tyre_flag(flags, "PRESSURE_LOW", "LF")
    assert ev["change_psi"] == 2.0


def test_shape_and_target_disagreeing_gives_one_cautious_flag():
    prof = {c: [76, 74, 66, 64, 64, 66, 74, 76] for c in CORNERS}
    flags = flags_for(profiles=prof, pressure_psi=38)
    lf = [f for f in flags if "LF" in f["tyres"] and f["category"] == "pressure" and f["action"]]
    assert [f["rule"] for f in lf] == ["PRESSURE_CONFLICT"]
    assert "Keep" in lf[0]["action"]


def test_cold_tyres_flagged_and_become_takeaway():
    flags = flags_for(profiles={c: [45] * 8 for c in CORNERS})
    cold = next(f for f in flags if f["rule"] == "TEMP_BELOW_WINDOW")
    assert cold["title"].startswith("All four")
    assert pick_takeaway(flags)["rule"] == "TEMP_BELOW_WINDOW"


def test_hot_tyres_flagged():
    flags = flags_for(profiles={c: [100] * 8 for c in CORNERS})
    assert "TEMP_ABOVE_WINDOW" in rules(flags)


def test_default_target_and_cold_pressure_give_a_start_pressure():
    flags = flags_for(context={"cold_pressure_front_psi": 30.0, "cold_pressure_rear_psi": 28.0}, pressure_psi=38)
    lf, ev = tyre_flag(flags, "PRESSURE_TARGET", "LF")
    assert ev["target_source"] == "default" and ev["recommended_cold_psi"] == 24.0
    assert "left-front by about 6.0 psi (30.0 → 24.0 psi)" in lf["action"] and lf["title"].startswith("Front tyres")
    build = next(f for f in flags if f["rule"] == "PRESSURE_BUILD")
    assert build["evidence"]["LR"]["cold_set_psi"] == 28.0


def test_flags_are_ranked_and_traceable():
    flags = flags_for(profiles={c: [45] * 8 for c in CORNERS})
    priorities = [f["priority"] for f in flags]
    assert priorities == sorted(priorities, reverse=True)
    for f in flags:
        assert f["id"].startswith("F") and f["rule"] and isinstance(f["evidence"], dict)


def test_target_hot_pressure_gives_recommended_cold_pressure():
    flags = flags_for(context={"target_hot_pressure_psi": 36.0, "cold_pressure_front_psi": 32.0}, pressure_psi=38)
    _, ev = tyre_flag(flags, "PRESSURE_TARGET", "LF")
    assert ev["recommended_cold_psi"] == 30.0
    rear, rev = tyre_flag(flags, "PRESSURE_TARGET", "LR")
    assert "Lower" in rear["action"] and rev["recommended_cold_psi"] is None
    assert rev["change_psi"] == -2.0


def test_uneven_axle_pressures_flagged():
    flags = flags_for(pressure_psi={"LF": 40, "RF": 36, "LR": 38, "RR": 38})
    split = [f for f in flags if f["rule"] == "PRESSURE_AXLE_SPLIT"]
    assert len(split) == 1 and set(split[0]["tyres"]) == {"LF", "RF"}


def test_suspension_hint_when_camber_and_pressure_look_right():
    front, rear = [90, 87, 84, 81, 78, 75, 72, 69], [75, 72, 69, 66, 63, 60, 57, 54]
    prof = {"LF": front, "RF": front, "LR": rear, "RR": rear}
    corner = {"LF": [79.5] * 8, "RF": [79.5] * 8, "LR": [64.5] * 8, "RR": [64.5] * 8}
    flags = flags_for(profiles=prof, corner_profiles=corner, pressure_psi=32)
    assert {"BALANCE_FRONT_HOT", "SUSPENSION_HINT"} <= rules(flags)
    hint = next(f for f in flags if f["rule"] == "SUSPENSION_HINT")
    assert "softer front anti-roll bar" in hint["action"]


def test_no_suspension_hint_when_camber_explains_it():
    straight = {"LF": [80] * 8, "RF": [80] * 8, "LR": [65] * 8, "RR": [65] * 8}
    corner = {**straight, "LF": [72, 74, 76, 78, 80, 82, 84, 86], "RF": [72, 74, 76, 78, 80, 82, 84, 86]}
    flags = flags_for(profiles=straight, corner_profiles=corner)
    assert "CAMBER_ADD" in rules(flags) and "SUSPENSION_HINT" not in rules(flags)


def test_driver_grip_use_compares_best_and_typical_laps():
    st = compute_stats(parse_session(make_csv().encode(), "t.csv"), CFG)
    st["lap_summary"].update(best_lap_braking_g=1.10, typical_braking_g=0.98, best_lap_cornering_g=1.40, typical_cornering_g=1.38)
    f = next(f for f in run_rules(st, CFG, {}) if f["rule"] == "DRIVER_GRIP_USE")
    assert "braking" in f["title"] and "cornering" not in f["title"]


def test_every_flag_explains_why():
    flags = flags_for(profiles={c: [45] * 8 for c in CORNERS})
    for f in flags:
        if f["rule"] != "BEST_LAP":
            assert f["why"], f["rule"]


def test_setup_sheet_matches_flags():
    from backend.rules import setup_sheet
    st = compute_stats(parse_session(make_csv(profiles={c: [70] * 8 for c in CORNERS}, pressure_psi=30).encode(), "t.csv"), CFG)
    flags = run_rules(st, CFG, {"cold_pressure_front_psi": 25.0})
    sheet = setup_sheet(st, flags, CFG, {"cold_pressure_front_psi": 25.0})
    lf = sheet["corners"]["LF"]
    assert lf["pressure"]["change_psi"] == 2.0 and lf["pressure"]["to_psi"] == 27.0
    assert lf["camber"]["direction"] == 1 and "Needs tools" in lf["camber"]["tools"]
    assert "No tools" in lf["pressure"]["tools"] and lf["heat_shape"]["key"] == "even"
    assert sheet["target_source"] == "default"


def test_same_finding_on_both_tyres_of_an_axle_is_merged():
    flags = flags_for(profiles={c: [70] * 8 for c in CORNERS}, pressure_psi=30)
    camber = [f for f in flags if f["rule"] == "CAMBER_STRAIGHT_LOW"]
    assert sorted(tuple(f["tyres"]) for f in camber) == [("LF", "RF"), ("LR", "RR")]
    target = [f for f in flags if f["rule"] == "PRESSURE_TARGET"]
    assert len(target) == 2 and all(len(f["tyres"]) == 2 for f in target)
