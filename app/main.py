"""AI Squat Analysis — FastAPI backend.

Endpoints:
  POST   /upload           -> {job_id}  (accepts video, starts background job)
  GET    /status/{job_id}  -> {status, progress, result or error}
  GET    /download/{job_id}/{file}  -> file download (annotated.mp4 / report.json)
  GET    /                 -> health
"""

from __future__ import annotations

import os
import uuid
import json
import threading
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import cv2
import numpy as np

from .cv.pose_estimator import PoseEstimator, to_pixel, pick_side
from .cv.rep_detector import detect_reps
from .cv.evaluator import evaluate_rep, build_frame_geometry, load_skill
from .cv.annotator import annotate_frame, build_uncertainty_notes
from .cv.pipeline import analyze_video

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
MAX_DURATION_SECONDS = 60          # assignment: duration limit
MAX_FILE_MB = 100
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory job store (thread-safe)
# ---------------------------------------------------------------------------
_jobs_lock = threading.Lock()
JOBS: Dict[str, Dict[str, Any]] = {}


def _new_job(job_id: str) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",           # queued | processing | completed | failed
        "progress": 0,                # 0..100
        "error": None,
        "filename": None,
        "duration_s": None,
        "fps": None,
        "frame_count": None,
        "reps": None,
        "report_path": None,
        "annotated_path": None,
        "created_at": None,
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="AI Squat Analysis", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the original uploaded video for preview
@app.get("/uploads/{filename}")
def get_upload(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Upload not found")
    return FileResponse(path)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


@app.get("/health")
def health():
    return {"ok": True, "service": "ai-squat-analysis", "version": "0.1.0"}


@app.get("/")
def index():
    """Serve the single-page frontend."""
    path = BASE_DIR / "app" / "static" / "index.html"
    if not path.exists():
        raise HTTPException(status_code=500, detail="Frontend not found")
    return FileResponse(path, media_type="text/html")


@app.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Accept a side-view squat video and start analysis."""
    ext = Path(file.filename or "video").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Read content to enforce size limit
    content = await file.read()
    if len(content) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (> {MAX_FILE_MB} MB)")

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        JOBS[job_id] = _new_job(job_id)
        JOBS[job_id]["filename"] = file.filename
        JOBS[job_id]["status"] = "queued"

    upload_path = UPLOAD_DIR / f"{job_id}{ext}"
    with open(upload_path, "wb") as f:
        f.write(content)

    background_tasks.add_task(_run_analysis, job_id, str(upload_path))
    return {"job_id": job_id, "status": "queued", "filename": file.filename}


@app.get("/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"],
        "filename": job["filename"],
        "duration_s": job["duration_s"],
        "fps": job["fps"],
        "frame_count": job["frame_count"],
        "reps": job["reps"],
        "viewpoint": job.get("viewpoint"),
        "skill": job.get("skill"),
        "camera_roll_deg": job.get("camera_roll_deg"),
        "has_report": job["report_path"] is not None,
        "has_annotated_video": job["annotated_path"] is not None,
    }


@app.get("/download/{job_id}/{kind}")
def download(job_id: str, kind: str):
    """kind: 'video' or 'report'"""
    with _jobs_lock:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    if kind == "video":
        path = job["annotated_path"]
        media_type = "video/mp4"
        filename = "annotated_squat.mp4"
    elif kind == "report":
        path = job["report_path"]
        media_type = "application/json"
        filename = "squat_report.json"
    else:
        raise HTTPException(status_code=400, detail="Invalid kind")

    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# Background analysis pipeline
# ---------------------------------------------------------------------------

def _run_analysis(job_id: str, upload_path: str):
    """Full CV pipeline executed in a background thread."""
    def set_progress(p: int, status: Optional[str] = None, **fields):
        with _jobs_lock:
            JOBS[job_id]["progress"] = p
            if status:
                JOBS[job_id]["status"] = status
            for k, v in fields.items():
                JOBS[job_id][k] = v

    try:
        set_progress(2, status="processing")

        def cb(pct, stage=""):
            set_progress(pct)

        report, annotated_path, reps = analyze_video(
            upload_path, progress_cb=cb, output_dir=str(OUTPUT_DIR))

        report_name = f"{job_id}_report.json"
        report_path = str(OUTPUT_DIR / report_name)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        set_progress(100, status="completed",
                     reps=reps,
                     report_path=report_path,
                     annotated_path=annotated_path,
                     duration_s=report.get("duration_s"),
                     fps=report.get("fps"),
                     frame_count=report.get("frame_count"),
                     viewpoint=report.get("viewpoint"),
                     skill=report.get("skill"),
                     camera_roll_deg=report.get("camera_roll_deg"))

    except Exception as exc:  # noqa: BLE001
        with _jobs_lock:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(exc)
            JOBS[job_id]["progress"] = 100
