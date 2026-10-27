import numpy as np

from backend.ingest import parse_session
from backend.pipeline import load_config
from backend.stats import compute_stats, detect_off_tread, edge_summary

from .synth import CORNERS, make_csv

CFG = load_config()


def stats_for(**kw):
    return compute_stats(parse_session(make_csv(**kw).encode(), "t.csv"), CFG)


def test_known_profile_gives_known_edges():
    grad = [80, 78, 76, 74, 72, 70, 68, 66]
    st = stats_for(profiles={c: grad for c in CORNERS})
    lf = st["tyres"]["LF"]
    assert lf["average_c"] == 73.0
    assert lf["straight"]["inner"] == 79.0
    assert lf["straight"]["outer"] == 67.0
    assert lf["straight"]["inner_minus_outer"] == 12.0
    assert lf["share_in_window"] == 1.0


def test_corner_profile_uses_outside_tyre():
    flat = [70] * 8
    outer_hot = [60, 62, 64, 66, 68, 70, 72, 74]
    st = stats_for(profiles={c: flat for c in CORNERS}, corner_profiles={c: outer_hot for c in CORNERS})
    for c in CORNERS:
        assert st["tyres"][c]["corner_loaded"]["inner_minus_outer"] == -12.0
        assert st["tyres"][c]["straight"]["inner_minus_outer"] == 0.0


def test_spikes_are_removed():
    st = stats_for(spikes=50)
    assert st["data_quality"]["temperature"]["LF"]["spikes_removed"] >= 50
    assert st["tyres"]["LF"]["peak_c"] == 60.0


def test_off_tread_edge_zone_detected():
    assert detect_off_tread(np.array([45, 45, 44, 46, 44, 45, 45, 25.0]), CFG) == [8]
    assert detect_off_tread(np.array([33, 41, 55, 55, 56, 55, 55, 50.0]), CFG) == [1, 2]
    assert detect_off_tread(np.array([80, 78, 76, 74, 72, 70, 68, 66.0]), CFG) == []


def test_edge_summary_skips_excluded_zones():
    e = edge_summary(np.array([np.nan, np.nan, 60, 60, 62, 62, 58, 58.0]))
    assert e["inner"] == 60.0 and e["outer"] == 58.0 and e["middle"] == 62.0


def test_laps_exclude_out_and_in_lap():
    st = stats_for(laps=6, lap_time=90.0)
    ls = st["lap_summary"]
    assert ls["count"] == 6
    assert ls["best_time_s"] == 90.0
    assert ls["warmup"] == 2 and ls["clean"] == 4


def test_pressure_scaled_to_psi():
    st = stats_for(pressure_psi=38.0)
    assert st["tyres"]["RF"]["pressure_psi"]["hot"] == 38.0


def test_deterministic():
    a = stats_for(spikes=10)
    b = stats_for(spikes=10)
    assert a == b


def test_frozen_pressure_sensor_is_ignored():
    st = stats_for(pressure_psi={"LF": 38, "RF": 38, "LR": 38, "RR": 19.8}, frozen_pressure=("RR",))
    assert st["data_quality"]["pressure_frozen"] == ["RR"]
    assert st["tyres"]["RR"]["pressure_psi"] is None and st["tyres"]["LR"]["pressure_psi"]["hot"] == 38.0


def test_peak_must_be_held_for_half_a_second():
    from backend.stats import _held_max
    values = np.full(200, 60.0)
    values[50:53] = 80.0
    values[100:115] = 70.0
    assert _held_max(values, np.ones(200, dtype=bool), 10) == 70.0


def test_each_driving_state_has_its_own_numbers():
    straight = {c: [60] * 8 for c in CORNERS}
    corner = {c: [80] * 8 for c in CORNERS}
    st = stats_for(profiles=straight, corner_profiles=corner)
    v = st["tyres"]["LF"]["views"]
    assert v["straight"]["average_c"] == 60.0 and v["corner"]["average_c"] == 80.0
    assert v["corner"]["peak_c"] == 80.0 and st["tyres"]["LF"]["corner_peak_c"] == 80.0
    assert len(v["corner"]["zone_peaks"]) == 8


def test_driver_style_falls_back_to_g_force():
    st = stats_for()
    ds = st["driver_style"]
    assert ds["inputs"] == "G-force only"
    metrics = {m["key"]: m for m in ds["metrics"]}
    assert metrics["full_throttle_pct"]["typical"] is None and metrics["braking_g"]["key"] == "braking_g"
