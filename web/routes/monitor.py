import os
import subprocess
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path

from flask import Blueprint, current_app, request
from werkzeug.utils import secure_filename

from core.db import db
from core.models import AnalysisTask, TaskRun, VideoSource
from core.minio_client import upload_file_to_videos, download_file_from_videos, get_video_presigned_url
from core.task_service import create_analysis_task, get_task
from web.routes.response import error_response, success_response

monitor_bp = Blueprint("monitor", __name__, url_prefix="/api")

UPLOAD_DIR = Path("data/videos/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

_ffmpeg_procs: dict[int, subprocess.Popen] = {}

HLS_READY_URL = "http://127.0.0.1:8888/pedestrian/index.m3u8"
HLS_READY_TIMEOUT_SEC = 15.0
HLS_READY_INTERVAL_SEC = 0.5


def _wait_hls_ready(url: str, timeout: float, interval: float, ffmpeg_proc: subprocess.Popen | None = None) -> bool:
    """Poll MediaMTX HLS endpoint until the playlist is served.

    Returns True when the endpoint returns HTTP 2xx and the body starts with
    ``#EXTM3U`` (a valid HLS playlist). Returns False on timeout or when the
    FFmpeg pusher process has already exited (no point in waiting further).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ffmpeg_proc is not None and ffmpeg_proc.poll() is not None:
            return False
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if 200 <= resp.status < 300:
                    body = resp.read(64)
                    if b"#EXTM3U" in body:
                        return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(interval)
    return False


def _allowed_file(filename):
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


@monitor_bp.route("/upload", methods=["POST"])
def upload_video():
    if "file" not in request.files:
        return error_response("NO_FILE", "No file in request", status_code=400)
    file = request.files["file"]
    if file.filename == "" or not _allowed_file(file.filename):
        return error_response(
            "INVALID_FILE",
            "File must be .mp4, .avi, .mov, .mkv, or .webm",
            status_code=400,
        )

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    save_path = UPLOAD_DIR / filename
    file.save(str(save_path))

    # Upload to MinIO videos bucket
    minio_obj = upload_file_to_videos(filename, str(save_path))
    storage_uri = f"videos/{filename}" if minio_obj else ""

    unique_name = f"{file.filename} · {uuid.uuid4().hex[:6]}"
    source = VideoSource(
        name=unique_name,
        source_type="local_file",
        url=str(save_path),
        storage_uri=storage_uri,
    )
    db.session.add(source)
    db.session.commit()

    task = create_analysis_task({
            "name": file.filename,
            "source_url": str(save_path),
            "source_type": "local_file",
            "source_id": source.id,
        })
    db.session.add(task)
    db.session.commit()

    return success_response(
        {
            "task_id": task.id,
            "source_id": source.id,
            "filename": file.filename,
            "path": str(save_path),
        },
        status_code=201,
    )


@monitor_bp.route("/analysis-tasks/<int:task_id>/start-pipeline", methods=["POST"])
def start_pipeline(task_id: int):
    task = get_task(task_id)
    if task is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)

    # AnalysisTask has no `status` column; use latest TaskRun instead.
    latest_run = (
        TaskRun.query.filter(TaskRun.task_id == task.id)
        .order_by(TaskRun.created_at.desc())
        .first()
    )
    if latest_run is not None and latest_run.status in ("starting", "running"):
        return error_response(
            "INVALID_STATUS",
            f"Task already has a run in status {latest_run.status}",
            status_code=409,
        )

    source_path = task.source_url
    if not source_path or not Path(source_path).exists():
        return error_response(
            "FILE_NOT_FOUND",
            f"Video file not found: {source_path}",
            status_code=400,
        )

    from core.task_service import _build_config_snapshot
    from datetime import datetime as _dt
    run = TaskRun(task_id=task.id, status="starting", config_snapshot=_build_config_snapshot(task), started_at=_dt.now())
    db.session.add(run)
    db.session.commit()

    rtsp_url = "rtsp://127.0.0.1:8554/pedestrian"
    push_proc = subprocess.Popen(
        [
            "ffmpeg", "-re", "-stream_loop", "-1", "-i", source_path,
            "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-b:v", "2M", "-g", "50", "-keyint_min", "50", "-sc_threshold", "0",
            "-vf", "scale=640:360",
            "-f", "rtsp", "-rtsp_transport", "tcp", rtsp_url,
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    _ffmpeg_procs[task.id] = push_proc

    # Poll MediaMTX HLS instead of a fixed sleep; if FFmpeg dies early we
    # bail out immediately with a clean 504 and rollback task status.
    ready = _wait_hls_ready(
        HLS_READY_URL,
        timeout=HLS_READY_TIMEOUT_SEC,
        interval=HLS_READY_INTERVAL_SEC,
        ffmpeg_proc=push_proc,
    )
    if not ready:
        if push_proc.poll() is None:
            push_proc.kill()
        _ffmpeg_procs.pop(task.id, None)
        run.status = "failed"
        db.session.commit()
        return error_response(
            "HLS_NOT_READY",
            f"MediaMTX HLS not ready within {HLS_READY_TIMEOUT_SEC}s",
            status_code=504,
        )

    manager = current_app.extensions["runtime_manager"]
    status = manager.start(task, run)

    run.status = "running"
    db.session.commit()

    return success_response(
        {
            "task_id": task.id,
            "run_id": run.id,
            "rtsp_url": rtsp_url,
            "hls_url": HLS_READY_URL,
            "status": status,
        },
        status_code=202,
    )


@monitor_bp.route("/analysis-tasks/<int:task_id>/stop-pipeline", methods=["POST"])
def stop_pipeline(task_id: int):
    task = get_task(task_id)
    if task is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)

    proc = _ffmpeg_procs.pop(task.id, None)
    if proc is not None:
        proc.kill()

    manager = current_app.extensions["runtime_manager"]
    manager.stop(task_id)

    db.session.commit()

    return success_response({"task_id": task_id, "status": "stopped"})