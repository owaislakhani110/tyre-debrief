from __future__ import annotations

import numpy as np

CORNERS = ("LF", "RF", "LR", "RR")


def make_csv(
    profiles: dict[str, list[float]] | None = None,
    corner_profiles: dict[str, list[float]] | None = None,
    laps: int = 6,
    lap_time: float = 90.0,
    rate: int = 20,
    zero_temps: bool = False,
    spikes: int = 0,
    drop_channels: tuple[str, ...] = (),
    pressure_psi: float | dict = 38.0,
    frozen_pressure: tuple[str, ...] = (),
    pit_s: float = 0.0,
    temps_when: str = "always",
) -> str:
    base = [60, 60, 60, 60, 60, 60, 60, 60]
    profiles = profiles or {c: base for c in CORNERS}
    corner_profiles = corner_profiles or profiles
    out_lap, in_lap = 120.0 + pit_s, 130.0
    duration = out_lap + laps * lap_time + in_lap
    n = int(duration * rate)
    t = np.arange(n) / rate
    phase = (t // 5).astype(int) % 4
    lat = np.where(phase == 1, 1.0, np.where(phase == 3, -1.0, 0.0))
    yaw = np.where(phase == 1, 20.0, np.where(phase == 3, -20.0, 0.0))
    speed = np.full(n, 120.0)
    speed[t < 20 + pit_s] = 10.0
    speed[t > duration - 20] = 10.0

    cols = {"Time": t, "GPS Speed": speed, "GPS LatAcc": lat, "GPS Gyro": yaw, "AmbientTemp": np.full(n, 20.0)}
    loaded = {"LF": phase == 1, "LR": phase == 1, "RF": phase == 3, "RR": phase == 3}
    for c in CORNERS:
        for z in range(8):
            v = np.where(loaded[c], corner_profiles[c][z], profiles[c][z]).astype(float)
            if zero_temps:
                v[:] = 0.0
            elif temps_when != "always":
                v[(speed >= 40) == (temps_when == "stopped")] = 0.0
            cols[f"{c} Tyre Temp {z + 1:02d}"] = v
        cols[f"{c} Distance"] = np.full(n, 20.0)
        name = f"{c} Tyre Pressure" if c != "RF" else "RF Tyre Pressur"
        p = (pressure_psi[c] if isinstance(pressure_psi, dict) else pressure_psi) / 0.068948  # config pressure_scale_to_psi
        cols[name] = np.full(n, float(p)) if c in frozen_pressure else p + np.tile([-1.0, -0.5, 0.5, 1.0], n // 4 + 1)[:n]
        cols[f"{c} TPMS Temp"] = np.full(n, 50.0)
    if spikes:
        rng = np.random.default_rng(0)
        idx = rng.choice(np.arange(n // 4, n // 2), spikes, replace=False)
        cols["LF Tyre Temp 04"][idx] = 140.0
    for d in drop_channels:
        cols.pop(d, None)

    markers = [out_lap + i * lap_time for i in range(laps + 1)] + [duration]
    lines = [
        '"Format","AiM CSV File"', '"Session","Synthetic"', '"Vehicle","Test Car"', '"Racer","Tester"',
        '"Championship",""', '"Comment",""', '"Date","Monday, January 5, 2026"', '"Time","9:00 AM"',
        f'"Sample Rate","{rate}"', f'"Duration","{duration}"', '"Segment","Session"',
        '"Beacon Markers",' + ",".join(f'"{m}"' for m in markers),
        '"Segment Times","x"', "",
        ",".join(f'"{k}"' for k in cols), ",".join('"u"' for _ in cols),
    ]
    data = np.column_stack(list(cols.values()))
    lines += [",".join(f"{x:.3f}" for x in row) for row in data]
    return "\r\n".join(lines) + "\r\n"
