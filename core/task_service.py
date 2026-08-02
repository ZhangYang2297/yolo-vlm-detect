from datetime import datetime
from typing import Optional, List
from core.db import db
from core.models import AnalysisTask, TaskRun
from core.logger import get_logger

logger = get_logger(__name__)


class TaskServiceError(Exception):
    pass


def _build_config_snapshot(task: AnalysisTask) -> dict:
    """Build an immutable config snapshot from the current task config."""
    return {
        "source_url": task.source_url,
        "source_type": task.source_type,
        "source_id": task.source_id,
        "detect_classes": task.detect_classes or [],
        "target_actions": task.target_actions or [],
        "scene_description": task.scene_description or "",
        "vlm_mode": task.vlm_mode or "small_crop",
        "audio_enabled": task.audio_enabled,
        "record_video": task.record_video,
        "roi_points": task.roi_points or [],
        "rule_doc_ids": task.rule_doc_ids or [],
    }


def create_analysis_task(data: dict) -> AnalysisTask:
    """Create a new analysis task."""
    name = data.get("name", "").strip()
    if not name:
        raise TaskServiceError("name is required")
    source_url = data.get("source_url", "").strip()
    if not source_url:
        raise TaskServiceError("source_url is required")

    task = AnalysisTask(
        name=name,
        source_url=source_url,
        source_type=data.get("source_type", "video"),
        source_id=data.get("source_id"),
        detect_classes=data.get("detect_classes", ["person"]),
        target_actions=data.get("target_actions", []),
        scene_description=data.get("scene_description", ""),
        vlm_mode=data.get("vlm_mode", "small_crop"),
        audio_enabled=data.get("audio_enabled", True),
        record_video=data.get("record_video", False),
        roi_points=data.get("roi_points", []),
        rule_doc_ids=data.get("rule_doc_ids", []),
    )
    db.session.add(task)
    db.session.commit()
    logger.info("task_created", task_id=task.id, name=name)
    return task


def get_task(task_id: int) -> Optional[AnalysisTask]:
    """Get a task by ID."""
    return db.session.get(AnalysisTask, task_id)


def list_tasks(limit: int | None = None) -> List[AnalysisTask]:
    """List all tasks."""
    q = AnalysisTask.query.order_by(AnalysisTask.created_at.desc())
    if limit is not None and limit > 0:
        q = q.limit(limit)
    return q.all()


def get_latest_run(task_id: int) -> Optional[TaskRun]:
    """Return the most recent TaskRun for a task, or None."""
    return (
        TaskRun.query.filter(TaskRun.task_id == task_id)
        .order_by(TaskRun.created_at.desc())
        .first()
    )


def start_task(task_id: int) -> TaskRun:
    """Start a task. Creates a new TaskRun with config snapshot.
    Idempotent: if already starting, returns the existing run.
    """
    task = get_task(task_id)
    if task is None:
        raise TaskServiceError(f"Task {task_id} not found")

    # Check for existing run in starting state
    existing = TaskRun.query.filter(
        TaskRun.task_id == task_id,
        TaskRun.status.in_(["starting", "running"]),
    ).first()
    if existing:
        logger.info("task_start_idempotent", task_id=task_id, run_id=existing.id)
        return existing

    snapshot = _build_config_snapshot(task)
    run = TaskRun(
        task_id=task_id,
        status="starting",
        config_snapshot=snapshot,
        started_at=datetime.now(),
    )
    db.session.add(run)
    db.session.commit()
    logger.info("task_started", task_id=task_id, run_id=run.id)
    return run


def stop_task(task_id: int) -> TaskRun:
    """Stop a running task."""
    task = get_task(task_id)
    if task is None:
        raise TaskServiceError(f"Task {task_id} not found")

    run = TaskRun.query.filter(
        TaskRun.task_id == task_id,
        TaskRun.status.in_(["starting", "running"]),
    ).order_by(TaskRun.created_at.desc()).first()
    if run is None:
        raise TaskServiceError(f"Task {task_id} is not running")

    run.status = "stopping"
    run.stopped_at = datetime.now()
    db.session.commit()
    logger.info("task_stopped", task_id=task_id, run_id=run.id)
    return run


def get_task_runs(task_id: int) -> List[TaskRun]:
    """Get all runs for a task, ordered by creation time desc."""
    return TaskRun.query.filter(
        TaskRun.task_id == task_id
    ).order_by(TaskRun.created_at.desc()).all()
