import pytest
from fastapi.testclient import TestClient

from backend import storage

from .synth import CORNERS, make_csv


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("DEBRIEF_DISABLE_LLM", "1")
    from backend.main import app
    return TestClient(app)


def upload(client, csv: str, name="session.csv", **form):
    return client.post("/api/reports", files={"file": (name, csv.encode(), "text/csv")}, data=form)


def test_upload_creates_report_and_history(client):
    r = upload(client, make_csv(profiles={c: [45] * 8 for c in CORNERS}), make="BMW", drivetrain="RWD",
               cold_pressure_front_psi="30")
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    report = client.get(f"/api/reports/{rid}").json()
    assert report["context"] == {"make": "BMW", "drivetrain": "RWD", "cold_pressure_front_psi": 30.0}
    assert report["narrative"]["takeaway"]
    assert report["timings"]["total_s"] < 15
    assert client.post("/api/reports/summaries", json={"ids": [rid]}).json()[0]["id"] == rid
    assert client.get("/api/reports").status_code == 405
    assert client.post("/api/reports/summaries", json={"ids": ["not-mine"]}).json() == []
    assert client.delete(f"/api/reports/{rid}").status_code == 200
    assert client.get(f"/api/reports/{rid}").status_code == 404


def test_rejects_unsupported_file_type(client):
    assert upload(client, "x", name="session.txt").status_code == 400


def test_broken_xrk_returns_readable_error(client):
    r = upload(client, "<hCNF garbage", name="session.xrk")
    assert r.status_code == 422 and "XRK" in r.json()["detail"]


def test_malformed_csv_returns_readable_error(client):
    r = upload(client, "hello,world\n1,2\n")
    assert r.status_code == 422
    assert "AiM CSV export" in r.json()["detail"]


def test_bad_number_in_form(client):
    r = upload(client, make_csv(), camber_front_deg="lots")
    assert r.status_code == 422


def test_frontend_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/status").json()["temperature_window"]["low_c"] == 60


def test_samples_listing_and_traversal_guard(client, tmp_path, monkeypatch):
    from backend import main
    monkeypatch.setattr(main, "SAMPLES_DIR", tmp_path)
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "demo.csv").write_text(make_csv(profiles={c: [70] * 8 for c in CORNERS}))
    listing = client.get("/api/samples").json()
    assert listing[0]["name"] == "demo.csv" and listing[0]["racer"] == "Tester"
    assert client.post("/api/samples/demo.csv").status_code == 200
    assert client.post("/api/samples/..%2Fsecret.csv").status_code == 404


def test_ai_debrief_arrives_after_the_report(client, monkeypatch):
    import time
    from backend import pipeline
    monkeypatch.setattr(pipeline, "configured_providers", lambda: ["gemini"])
    monkeypatch.setattr(pipeline, "generate_debrief", lambda *a, **k: {
        "headline": "AI headline", "summary": "AI summary.", "tyre_notes": [], "takeaway": "Do it.",
        "takeaway_flag_id": None, "cited_flag_ids": [], "source": "llm", "provider": "gemini", "model": "m", "attempts": []})
    rid = upload(client, make_csv()).json()["id"]
    first = client.get(f"/api/reports/{rid}").json()["narrative"]
    assert first["source"] in ("pending", "llm")
    for _ in range(50):
        n = client.get(f"/api/reports/{rid}").json()["narrative"]
        if n["source"] == "llm":
            break
        time.sleep(0.1)
    assert n["headline"] == "AI headline"
    assert client.post("/api/reports/summaries", json={"ids": [rid]}).json()[0]["headline"] == "AI headline"


def test_ask_endpoint(client):
    rid = upload(client, make_csv()).json()["id"]
    r = client.post(f"/api/reports/{rid}/ask", json={"question": "Why are my tyres cold?"})
    assert r.status_code == 200 and r.json()["answerable"] is False
    assert client.post(f"/api/reports/{rid}/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/reports/nope/ask", json={"question": "Why?"}).status_code == 404
