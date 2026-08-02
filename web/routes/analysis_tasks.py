from flask import Blueprint, current_app, request
from web.routes.response import success_response, error_response
from core.task_service import (
    create_analysis_task, get_task, list_tasks,
    start_task, stop_task, get_task_runs, get_latest_run,
    TaskServiceError,
)
from sqlalchemy import func
from core.db import db
from core.models import AlarmRecord
from core.media_source_validator import sanitize_credentials

analysis_tasks_bp = Blueprint("analysis_tasks", __name__, url_prefix="/api/analysis-tasks")


@analysis_tasks_bp.route("", methods=["GET"])
def list_analysis_tasks():
    """List tasks, most recent first. Supports ?limit=N and includes latest run summary."""
    limit_raw = request.args.get("limit", type=int)
    limit = limit_raw if limit_raw and limit_raw > 0 else None
    tasks = list_tasks(limit=limit)
    task_ids = [t.id for t in tasks]
    alarm_counts = {}
    if task_ids:
        for tid, cnt in db.session.query(AlarmRecord.task_id, func.count(AlarmRecord.id)).filter(AlarmRecord.task_id.in_(task_ids)).group_by(AlarmRecord.task_id).all():
            alarm_counts[tid] = cnt
    rows = []
    for t in tasks:
        latest = get_latest_run(t.id)
        rows.append({
            "id": t.id,
            "name": t.name,
            "source_url": sanitize_credentials(t.source_url),
            "source_type": t.source_type,
            "source_id": t.source_id,
            "detect_classes": t.detect_classes,
            "enabled": t.enabled,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "alarm_count": alarm_counts.get(t.id, 0),
            "storage_uri": t.video_source.storage_uri if t.video_source else None,
            "latest_run": {
                "id": latest.id,
                "status": latest.status,
                "started_at": latest.started_at.isoformat() if latest.started_at else None,
                "stopped_at": latest.stopped_at.isoformat() if latest.stopped_at else None,
            } if latest is not None else None,
        })
    return success_response(rows)


@analysis_tasks_bp.route("", methods=["POST"])
def create_analysis_task_route():
    data = request.get_json(silent=True)
    if not data:
        return error_response("INVALID_JSON", "Request body must be valid JSON")
    try:
        task = create_analysis_task(data)
        return success_response({
            "id": task.id,
            "name": task.name,
            "source_url": sanitize_credentials(task.source_url),
            "source_type": task.source_type,
            "source_id": task.source_id,
            "detect_classes": task.detect_classes,
            "enabled": task.enabled,
        }, status_code=201)
    except TaskServiceError as e:
        return error_response("TASK_ERROR", str(e))


@analysis_tasks_bp.route("/<int:task_id>", methods=["GET"])
def get_analysis_task(task_id: int):
    task = get_task(task_id)
    if task is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)
    return success_response({
        "id": task.id,
        "name": task.name,
        "source_url": sanitize_credentials(task.source_url),
        "source_type": task.source_type,
        "source_id": task.source_id,
        "detect_classes": task.detect_classes,
        "storage_uri": task.video_source.storage_uri if task.video_source else None,
        "target_actions": task.target_actions,
        "scene_description": task.scene_description,
        "vlm_mode": task.vlm_mode,
        "audio_enabled": task.audio_enabled,
        "record_video": task.record_video,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    })


@analysis_tasks_bp.route("/<int:task_id>/start", methods=["POST"])
def start_analysis_task(task_id: int):
    try:
        run = start_task(task_id)
        task = get_task(task_id)
        current_app.extensions["runtime_manager"].start(task, run)
        return success_response({
            "run_id": run.id,
            "task_id": run.task_id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
        }, status_code=202)
    except TaskServiceError as e:
        return error_response("TASK_ERROR", str(e), status_code=409)


@analysis_tasks_bp.route("/<int:task_id>/stop", methods=["POST"])
def stop_analysis_task(task_id: int):
    try:
        run = stop_task(task_id)
        current_app.extensions["runtime_manager"].stop(task_id)
        return success_response({
            "run_id": run.id,
            "task_id": run.task_id,
            "status": run.status,
            "stopped_at": run.stopped_at.isoformat() if run.stopped_at else None,
        }, status_code=202)
    except TaskServiceError as e:
        return error_response("TASK_ERROR", str(e), status_code=409)


@analysis_tasks_bp.route("/<int:task_id>/runs", methods=["GET"])
def list_task_runs(task_id: int):
    task = get_task(task_id)
    if task is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)
    runs = get_task_runs(task_id)
    return success_response([{
        "id": r.id,
        "task_id": r.task_id,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "stopped_at": r.stopped_at.isoformat() if r.stopped_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in runs])
