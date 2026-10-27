from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CORNERS = ("LF", "RF", "LR", "RR")
ZONES = 8


class IngestError(ValueError):
    pass


@dataclass
class Session:
    meta: dict
    data: pd.DataFrame
    lap_markers: list[float]
    warnings: list[str] = field(default_factory=list)


def zone_col(corner: str, zone: int) -> str:
    return f"{corner} Tyre Temp {zone:02d}"


OPTIONAL_CHANNELS = {
    "speed": r"^GPS Speed$",
    "lat_g": r"^GPS LatAcc$",
    "lon_g": r"^GPS LonAcc$",
    "steering": r"^SteeringAngle$",
    "throttle": r"^Pedal$",
    "brake_pressure": r"^BrakePressureF$",
    "ambient": r"^AmbientTemp$",
    "distance": r"^Distance on GPS Speed$",
    # AiM truncates channel names to 15 characters ("RF Tyre Pressur").
    **{f"{c}_pressure": rf"^{c} Tyre Pressu" for c in CORNERS},
    **{f"{c}_tpms_temp": rf"^{c} TPMS Temp$" for c in CORNERS},
    **{f"{c}_sensor_distance": rf"^{c} Distance$" for c in CORNERS},
}
REQUIRED_CHANNELS = {"time": r"^Time$", **{zone_col(c, z): rf"^{zone_col(c, z)}$" for c in CORNERS for z in range(1, ZONES + 1)}}


def _read_header(lines) -> tuple[dict, int, list[str]]:
    meta: dict[str, list[str]] = {}
    for i, line in enumerate(lines):
        row = next(csv.reader([line]), [])
        # The metadata block has its own two-column "Time" row.
        if row and row[0] == "Time" and len(row) > 5:
            return meta, i, row
        if row and row[0]:
            meta[row[0]] = row[1:]
        if i > 200:
            break
    raise IngestError("This doesn't look like a Wheel Turtle / AiM CSV export: no channel header row was found.")


def _map_columns(header: list[str]) -> tuple[dict[str, str], list[str]]:
    mapping, missing = {}, []
    for name, pattern in {**REQUIRED_CHANNELS, **OPTIONAL_CHANNELS}.items():
        hit = next((h for h in header if re.match(pattern, h)), None)
        if hit:
            mapping[name] = hit
        elif name in REQUIRED_CHANNELS:
            missing.append(name)
    return mapping, missing


def _seconds(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


XRK_MAGIC = b"<hCNF"
XRK_RATE_HZ = 20
BAR_TO_PSI = 14.5038
XRK_CHANNELS = {
    "GPS_LateralAcc": "lat_g",
    "GPS_InlineAcc": "lon_g",
    "SteeringAngle": "steering",
    "Pedal": "throttle",
    "BrakePressureF": "brake_pressure",
    "AmbientTemp": "ambient",
    **{f"{c}_Tyre_Temp_{z:02d}": zone_col(c, z) for c in CORNERS for z in range(1, ZONES + 1)},
    **{f"{c}_Tyre_Pressur{'e' if c != 'RF' else ''}": f"{c}_pressure" for c in CORNERS},
    **{f"{c}_TPMS_Temp": f"{c}_tpms_temp" for c in CORNERS},
    **{f"{c}_Distance": f"{c}_sensor_distance" for c in CORNERS},
}


def _is_xrk(source, filename: str) -> bool:
    if filename.lower().endswith((".xrk", ".xrz")):
        return True
    if isinstance(source, (bytes, bytearray)):
        return bytes(source[:5]) == XRK_MAGIC
    if isinstance(source, str) or hasattr(source, "__fspath__"):
        with open(source, "rb") as fh:
            return fh.read(5) == XRK_MAGIC
    head = source.read(5)
    source.seek(0)
    return head == XRK_MAGIC


def parse_xrk(source, filename: str = "") -> Session:
    import contextlib

    import libxrk
    import pyarrow as pa

    if not (isinstance(source, (str, bytes, bytearray)) or hasattr(source, "__fspath__")):
        source = source.read()
    try:
        # libxrk prints a warning for every channel with an unrecognised unit.
        with contextlib.redirect_stdout(io.StringIO()):
            log = libxrk.aim_xrk(bytes(source) if isinstance(source, bytearray) else source)
    except Exception as exc:
        raise IngestError(f"The XRK file could not be decoded ({type(exc).__name__}). Try exporting it as CSV from Race Studio.") from exc

    names = set(log.channels)
    missing = sorted({c for c in CORNERS if f"{c}_Tyre_Temp_01" not in names})
    if missing:
        raise IngestError(f"The XRK file is missing required channels (no tyre-temperature channels for {', '.join(missing)}). "
                          "Check the Wheel Turtle sensors are configured on the logger.")
    end_ms = max(int(log.channels[n].column("timecodes")[-1].as_py()) for n in names if log.channels[n].num_rows)
    timeline = np.arange(0, end_ms + 1, 1000 // XRK_RATE_HZ, dtype="int64")
    wanted = [n for n in list(XRK_CHANNELS) + ["GPS Speed"] if n in names]
    with contextlib.redirect_stdout(io.StringIO()):
        res = log.resample_to_timecodes(pa.array(timeline), channel_names=wanted)

    def col(name):
        return res.channels[name].column(name).to_numpy(zero_copy_only=False).astype(float)

    df = pd.DataFrame({"time": timeline / 1000.0})
    if "GPS Speed" in names:
        df["speed"] = col("GPS Speed") * 3.6  # m/s to km/h
    for src, dst in XRK_CHANNELS.items():
        if src in names:
            df[dst] = col(src)
    pressure_in_psi = False
    for c in CORNERS:
        if f"{c}_pressure" in df:
            unit = (res.channels[_xrk_name(c)].schema.field(_xrk_name(c)).metadata or {}).get(b"units", b"").decode()
            if unit == "bar":
                df[f"{c}_pressure"] *= BAR_TO_PSI
                pressure_in_psi = True
    if len(df) < 100:
        raise IngestError("The file contains too few data rows to analyse a session.")

    m = log.metadata
    laps = log.laps.to_pylist() if log.laps is not None else []
    meta = {
        "format": "AiM XRK",
        "session": m.get("Venue") or m.get("Session") or "",
        "vehicle": m.get("Vehicle", ""),
        "racer": m.get("Driver", ""),
        "championship": m.get("Series", "").strip(),
        "date": m.get("Log Date", ""),
        "start_time": m.get("Log Time", ""),
        "sample_rate_hz": float(XRK_RATE_HZ),
        "duration_s": end_ms / 1000.0,
        "filename": filename,
        "channels_found": sorted(c for c in df.columns if c in OPTIONAL_CHANNELS),
        "pressure_in_psi": pressure_in_psi,
    }
    markers = [lap["end_time"] / 1000.0 for lap in sorted(laps, key=lambda l: l["start_time"])]
    if markers:
        markers[-1] = max(markers[-1], meta["duration_s"])
    return Session(meta=meta, data=df, lap_markers=markers)


def _xrk_name(corner: str) -> str:
    return f"{corner}_Tyre_Pressur{'e' if corner != 'RF' else ''}"


def parse_session(source, filename: str = "") -> Session:
    if _is_xrk(source, filename):
        return parse_xrk(source, filename)
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    if isinstance(source, (str,)) or hasattr(source, "__fspath__"):
        fh = open(source, "r", newline="", encoding="utf-8-sig", errors="replace")
    else:
        fh = io.TextIOWrapper(source, encoding="utf-8-sig", errors="replace", newline="")
    with fh:
        try:
            meta_raw, header_idx, header = _read_header(fh)
        except UnicodeDecodeError as exc:
            raise IngestError("The file is not a text CSV export.") from exc
        mapping, missing = _map_columns(header)
        if missing:
            corners = sorted({m.split()[0] for m in missing if m != "time"})
            detail = f" (no tyre-temperature channels for {', '.join(corners)})" if corners else ""
            raise IngestError(f"The CSV is missing required channels{detail}. "
                              "Export the session with all Wheel Turtle channels enabled.")
        next(fh, None)
        try:
            df = pd.read_csv(fh, header=None, names=header, usecols=list(mapping.values()),
                             low_memory=False, on_bad_lines="skip")
        except (pd.errors.ParserError, ValueError) as exc:
            raise IngestError(f"The CSV data rows could not be read: {exc}") from exc

    df = df.rename(columns={v: k for k, v in mapping.items()}).apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["time"]).reset_index(drop=True)
    if len(df) < 100:
        raise IngestError("The file contains too few data rows to analyse a session.")

    meta = {
        "format": _first(meta_raw, "Format"),
        "session": _first(meta_raw, "Session"),
        "vehicle": _first(meta_raw, "Vehicle"),
        "racer": _first(meta_raw, "Racer"),
        "championship": _first(meta_raw, "Championship"),
        "date": _first(meta_raw, "Date"),
        "start_time": _first(meta_raw, "Time"),
        "sample_rate_hz": _seconds(_first(meta_raw, "Sample Rate")),
        "duration_s": _seconds(_first(meta_raw, "Duration")) or float(df["time"].iloc[-1]),
        "filename": filename,
        "channels_found": sorted(k for k in mapping if k in OPTIONAL_CHANNELS),
    }
    markers = [m for m in (_seconds(v) for v in meta_raw.get("Beacon Markers", [])) if m is not None]
    return Session(meta=meta, data=df, lap_markers=markers)


def _first(meta: dict, key: str) -> str:
    values = meta.get(key) or [""]
    return values[0].strip()


def zone_matrix(df: pd.DataFrame, corner: str) -> np.ndarray:
    return df[[zone_col(corner, z) for z in range(1, ZONES + 1)]].to_numpy(dtype=float)
