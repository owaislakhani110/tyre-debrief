from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from .ingest import IngestError, parse_session
from .narrative import answer_question, configured_providers
from .pipeline import CONTEXT_FIELDS, analyse, complete_narrative, load_config, session_problem

logging.basicConfig(level=logging.INFO)
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_UPLOAD_BYTES = 600 * 1024 * 1024

@asynccontextmanager
async def lifespan(_app):
    # Checking every sample means reading every file; do it before anyone opens the page.
    threading.Thread(target=list_samples, daemon=True).start()
    yield


app = FastAPI(title="Tyre Debrief Assistant", version="0.1.0", lifespan=lifespan)


def _save_and_narrate(report: dict) -> str:
    rid = storage.save_report(report)
    if report["narrative"]["source"] == "pending":
        # The report is usable straight away; the AI debrief replaces the template when it's ready.
        threading.Thread(target=lambda: storage.update_narrative(rid, complete_narrative(report)), daemon=True).start()
    return rid


@app.post("/api/reports")
async def create_report(
    file: UploadFile = File(...),
    make: str = Form(""), model: str = Form(""), drivetrain: str = Form(""),
    tyre_compound: str = Form(""), camber_front_deg: str = Form(""), camber_rear_deg: str = Form(""),
    cold_pressure_front_psi: str = Form(""), cold_pressure_rear_psi: str = Form(""),
    target_hot_pressure_psi: str = Form(""), session_type: str = Form(""), notes: str = Form(""),
):
    if not (file.filename or "").lower().endswith((".csv", ".xrk", ".xrz")):
        raise HTTPException(400, "Please upload a session file: an AiM .csv export or the logger's .xrk/.xrz file.")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That file is larger than 600 MB.")
    ctx = dict(zip(CONTEXT_FIELDS, (make, model, drivetrain, tyre_compound, camber_front_deg, camber_rear_deg,
                                    cold_pressure_front_psi, cold_pressure_rear_psi, target_hot_pressure_psi,
                                    session_type, notes)))
    try:
        report = await run_in_threadpool(analyse, file.file, file.filename, ctx, None, "deferred")
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return {"id": _save_and_narrate(report), "timings": report["timings"]}


class IdList(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


@app.post("/api/reports/summaries")
def report_summaries(body: IdList):
    return storage.summaries(body.ids)


@app.get("/api/reports/{rid}")
def get_report(rid: str):
    report = storage.get_report(rid)
    if not report:
        raise HTTPException(404, "Report not found.")
    return report


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=300)


@app.post("/api/reports/{rid}/ask")
async def ask(rid: str, body: Question):
    report = storage.get_report(rid)
    if not report:
        raise HTTPException(404, "Report not found.")
    return await run_in_threadpool(answer_question, report, body.question.strip())


@app.delete("/api/reports/{rid}")
def delete_report(rid: str):
    if not storage.delete_report(rid):
        raise HTTPException(404, "Report not found.")
    return {"deleted": rid}


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data"


def _sample_files() -> dict[str, Path]:
    files = sorted(SAMPLES_DIR.glob("raw/*.csv")) + sorted(SAMPLES_DIR.glob("xrk/*.xr[kz]")) + sorted(SAMPLES_DIR.glob("*.csv"))
    return {p.name: p for p in files}


@lru_cache(maxsize=256)
def _sample_info(path_str: str, mtime: float) -> dict:
    path = Path(path_str)
    try:
        session = parse_session(path, path.name)
        problem = session_problem(session, load_config())
        m = session.meta
    except IngestError as exc:
        return {"racer": None, "track": None, "date": None, "problem": str(exc)}
    return {"racer": m["racer"], "track": m["session"], "date": m["date"], "problem": problem}


@app.get("/api/samples")
def list_samples():
    out = []
    for name, path in _sample_files().items():
        info = _sample_info(str(path), path.stat().st_mtime)
        out.append({"name": name, **info, "format": path.suffix.lstrip(".").upper(),
                    "size_mb": round(path.stat().st_size / 1e6, 1)})
    return out


@app.post("/api/samples/{name}")
async def analyse_sample(name: str):
    path = _sample_files().get(name)
    if not path:
        raise HTTPException(404, "Sample not found.")
    try:
        report = await run_in_threadpool(analyse, path, name, {"make": "BMW", "model": "M3 F80", "drivetrain": "RWD"},
                                         None, "deferred")
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return {"id": _save_and_narrate(report), "timings": report["timings"]}


@app.get("/api/status")
def status():
    cfg = load_config()
    providers = configured_providers()
    return {"llm_enabled": bool(providers), "providers": providers, "temperature_window": cfg["temperature_window"]}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/report")
def report_page():
    return FileResponse(FRONTEND / "report.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
