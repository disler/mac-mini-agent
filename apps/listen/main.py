import fcntl
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent.parent / ".env")

app = FastAPI()

JOBS_DIR = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
ARCHIVED_DIR = JOBS_DIR / "archived"

_JOB_ID_RE = re.compile(r"^[0-9a-f]{8}$")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_auth(api_key: str = Security(_api_key_header)) -> None:
    """Require a valid X-API-Key header matching LISTEN_API_KEY in the environment."""
    expected = os.environ.get("LISTEN_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="LISTEN_API_KEY not configured on server")
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_job_id(job_id: str) -> Path:
    """Validate job_id format and return the resolved job file path.

    Enforces a strict ^[0-9a-f]{8}$ pattern and additionally checks that
    the resolved path stays inside JOBS_DIR to guard against path traversal.
    """
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    job_file = JOBS_DIR / f"{job_id}.yaml"
    if not job_file.resolve().is_relative_to(JOBS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    return job_file


def _read_job(path: Path) -> dict:
    with open(path) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        return yaml.safe_load(f)


def _write_job(path: Path, data: dict) -> None:
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


class JobRequest(BaseModel):
    prompt: str


@app.post("/job", dependencies=[Depends(_require_auth)])
def create_job(req: JobRequest):
    job_id = uuid4().hex[:8]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    job_data = {
        "id": job_id,
        "status": "running",
        "prompt": req.prompt,
        "created_at": now,
        "pid": 0,
        "updates": [],
        "summary": "",
    }

    job_file = JOBS_DIR / f"{job_id}.yaml"
    # Initial write — no lock needed; file is brand new
    with open(job_file, "w") as f:
        yaml.dump(job_data, f, default_flow_style=False, sort_keys=False)

    # Spawn worker — prompt is read from YAML by the worker, not passed as argv
    # (argv is visible to all users via ps aux for the process lifetime)
    worker_path = Path(__file__).parent / "worker.py"
    proc = subprocess.Popen(
        [sys.executable, str(worker_path), job_id],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Update PID with exclusive lock to avoid racing the worker's session write
    job_data["pid"] = proc.pid
    _write_job(job_file, job_data)

    return {"job_id": job_id, "status": "running"}


@app.get("/job/{job_id}", response_class=PlainTextResponse, dependencies=[Depends(_require_auth)])
def get_job(job_id: str):
    job_file = _validate_job_id(job_id)
    if not job_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return job_file.read_text()


@app.get("/jobs", response_class=PlainTextResponse, dependencies=[Depends(_require_auth)])
def list_jobs(archived: bool = False):
    search_dir = ARCHIVED_DIR if archived else JOBS_DIR
    jobs = []
    for f in sorted(search_dir.glob("*.yaml")):
        data = _read_job(f)
        jobs.append({
            "id": data.get("id"),
            "status": data.get("status"),
            "prompt": data.get("prompt"),
            "created_at": data.get("created_at"),
        })
    return yaml.dump({"jobs": jobs}, default_flow_style=False, sort_keys=False)


@app.post("/jobs/clear", dependencies=[Depends(_require_auth)])
def clear_jobs():
    ARCHIVED_DIR.mkdir(exist_ok=True)
    count = 0
    for f in JOBS_DIR.glob("*.yaml"):
        shutil.move(str(f), str(ARCHIVED_DIR / f.name))
        count += 1
    return {"archived": count}


@app.delete("/job/{job_id}", dependencies=[Depends(_require_auth)])
def stop_job(job_id: str):
    job_file = _validate_job_id(job_id)
    if not job_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    data = _read_job(job_file)
    pid = data.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    data["status"] = "stopped"
    _write_job(job_file, data)

    return {"job_id": job_id, "status": "stopped"}


if __name__ == "__main__":
    import uvicorn
    # Bind to localhost only — not exposed to the network by default.
    # Set LISTEN_HOST=0.0.0.0 only if you have added network-level access controls.
    host = os.environ.get("LISTEN_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=7600)
