import pytest

from backend.ingest import IngestError, parse_session
from backend.pipeline import analyse

from .synth import make_csv


def test_parses_metadata_and_channels():
    s = parse_session(make_csv().encode(), "synthetic.csv")
    assert s.meta["racer"] == "Tester"
    assert s.meta["vehicle"] == "Test Car"
    assert s.meta["start_time"] == "9:00 AM"
    assert s.meta["sample_rate_hz"] == 20
    assert "LF Tyre Temp 01" in s.data.columns
    assert len(s.lap_markers) == 8


def test_truncated_pressure_channel_name_is_mapped():
    s = parse_session(make_csv().encode())
    assert "RF_pressure" in s.data.columns


def test_missing_tyre_channels_gives_clear_error():
    csv = make_csv(drop_channels=tuple(f"RR Tyre Temp {z:02d}" for z in range(1, 9)))
    with pytest.raises(IngestError, match="RR"):
        parse_session(csv.encode())


def test_not_an_export_gives_clear_error():
    with pytest.raises(IngestError, match="AiM CSV export"):
        parse_session(b"name,age\nbob,3\n")


def test_too_few_rows():
    lines = make_csv().split("\r\n")
    header_end = next(i for i, l in enumerate(lines) if l.startswith('"Time","GPS Speed"')) + 2
    with pytest.raises(IngestError, match="too few"):
        parse_session("\r\n".join(lines[: header_end + 10]).encode())


def test_all_zero_temperatures_rejected():
    with pytest.raises(IngestError, match="every Wheel Turtle reading in the file is zero"):
        analyse(make_csv(zero_temps=True).encode(), "zero.csv", with_narrative=False)


def test_sensors_only_logging_while_stopped_rejected():
    with pytest.raises(IngestError, match="only reported while the car was stopped"):
        analyse(make_csv(temps_when="stopped").encode(), "parked.csv", with_narrative=False)


def test_long_pit_stay_with_good_track_data_accepted():
    r = analyse(make_csv(pit_s=3000, temps_when="moving").encode(), "long_pit.csv", with_narrative=False)
    assert r["stats"]["tyres"]["LF"]["average_c"] == 60.0


def test_paddock_recording_rejected():
    import re
    lines = make_csv().split("\r\n")
    hdr = next(i for i, l in enumerate(lines) if l.startswith('"Time","GPS Speed"'))
    slow = [re.sub(r"^([^,]*),[^,]*,", r"\1,5.000,", l) if i > hdr + 1 and l else l for i, l in enumerate(lines)]
    with pytest.raises(IngestError, match="no real track running"):
        analyse("\r\n".join(slow).encode(), "paddock.csv", with_narrative=False)
