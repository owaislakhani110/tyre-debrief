
import os
from pathlib import Path

import pytest

from backend.ingest import parse_session
from backend.pipeline import analyse, load_config
from backend.stats import compute_stats


DATA = Path(__file__).resolve().parent.parent / "data"

# Optional real-session files configured through environment variables.
# No private Team Plus filenames are stored in the repository.
XRK = DATA / "xrk" / os.getenv("TEST_XRK_FILE", "test_session.xrk")
CSV = DATA / "raw" / os.getenv("TEST_CSV_FILE", "test_session.csv")

needs_data = pytest.mark.skipif(
    not (XRK.exists() and CSV.exists()),
    reason="Optional real-session test files not available",
)


@needs_data
def test_xrk_matches_csv_export_of_same_session():
    cfg = load_config()

    a = compute_stats(parse_session(XRK, XRK.name), cfg)
    b = compute_stats(parse_session(CSV, CSV.name), cfg)

    assert a["lap_summary"]["count"] == b["lap_summary"]["count"]

    assert (
        abs(
            a["lap_summary"]["best_time_s"]
            - b["lap_summary"]["best_time_s"]
        )
        < 0.05
    )

    for c in ("LF", "RF", "LR", "RR"):
        assert (
            abs(
                a["tyres"][c]["average_c"]
                - b["tyres"][c]["average_c"]
            )
            < 0.5
        )

        pa = a["tyres"][c]["pressure_psi"]
        pb = b["tyres"][c]["pressure_psi"]

        assert (pa is None) == (pb is None)

        if pa:
            assert abs(pa["hot"] - pb["hot"]) < 0.3


@needs_data
def test_xrk_full_pipeline():
    r = analyse(XRK, XRK.name, with_narrative=False)

    assert r["stats"]["session"]["racer"]
    assert r["flags"]


def test_corrupt_xrk_gives_clear_error():
    from backend.ingest import IngestError

    with pytest.raises(IngestError, match="XRK"):
        parse_session(
            b"<hCNF" + b"\x00" * 200,
            "broken.xrk",
        )