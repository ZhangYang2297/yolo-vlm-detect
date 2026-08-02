from flask import Blueprint, request, jsonify
from datetime import datetime
from core.db import db
from core.models import AnalysisTask, AlarmRecord
from core.redis_client import publish
from core.video_source_service import create_video_source, VideoSourceURIError, VideoSourceConflictError
from core.media_source_validator import sanitize_credentials
from core.minio_client import get_presigned_url
from config.settings import get_settings

api_bp = Blueprint("api", __name__)
settings = get_settings()


def _error(message: str, code: int = 400):
    return jsonify({"error": message}), code


@api_bp.route("/tasks", methods=["GET"])
def list_tasks():
    tasks = AnalysisTask.query.order_by(AnalysisTask.created_at.desc()).all()
    return jsonify([
        {
            "id": t.id,
            "name": t.name,
            "source_url": t.source_url,
            "source_type": t.source_type,
            "enabled": t.enabled,
            "detect_classes": t.detect_classes,
            "target_actions": t.target_actions,
            "scene_description": t.scene_description,
            "audio_enabled": t.audio_enabled,
            "vlm_mode": t.vlm_mode,
            "stream_path": t.stream_path,
            "alarm_count": len(t.alarms),
            "created_at": t.created_at.isoformat(),
        }
        for t in tasks
    ])


@api_bp.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True)
    if not data:
        return _error("请求体必须是JSON格式")

    name = data.get("name", "").strip()
    source_url = data.get("source_url", "").strip()
    if not name:
        return _error("任务名称不能为空")
    if not source_url:
        return _error("视频源地址不能为空")
    if len(name) > 100:
        name = name[:100]

    # Auto-create VideoSource for backward compatibility
    source_id = None
    source_type = data.get("source_type", "video")
    try:
        vs = create_video_source({
            "name": name,
            "source_type": source_type,
            "url": source_url,
        })
        source_id = vs.id
    except (VideoSourceURIError, VideoSourceConflictError):
        pass  # Non-critical: new API recommended

    task = AnalysisTask(
        name=name,
        source_url=source_url[:500],
        source_type=source_type,
        source_id=source_id,
        detect_classes=data.get("detect_classes", ["person"])[:20],
        target_actions=data.get("target_actions", []),
        scene_description=str(data.get("scene_description", ""))[:2000],
        roi_points=data.get("roi_points", []),
        audio_enabled=data.get("audio_enabled", True),
        vlm_mode=data.get("vlm_mode", "small_crop"),
        stream_path=f"task_{int(datetime.now().timestamp())}",
    )
    db.session.add(task)
    db.session.commit()
    publish("task:created", {"task_id": task.id})
    response = jsonify({"id": task.id, "message": "任务创建成功"})
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/analysis-tasks>; rel="successor-version"'
    return response, 201


@api_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    task = AnalysisTask.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    publish("task:deleted", {"task_id": task_id})
    return jsonify({"message": "删除成功"})


@api_bp.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = AnalysisTask.query.get_or_404(task_id)
    task.enabled = not task.enabled
    db.session.commit()
    publish(f"task:{task_id}:update", {"enabled": task.enabled, "task_id": task_id})
    return jsonify({"id": task.id, "enabled": task.enabled})


@api_bp.route("/alarms", methods=["GET"])
def list_alarms():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 30, type=int), 200)
    severity = request.args.get("severity", "")
    status = request.args.get("status", "")
    alarm_type = request.args.get("type", "")

    query = AlarmRecord.query
    if severity:
        query = query.filter_by(severity=severity)
    if status:
        query = query.filter_by(status=status)
    if alarm_type:
        query = query.filter_by(alarm_type=alarm_type)

    pagination = query.order_by(AlarmRecord.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    items = []
    for a in pagination.items:
        item = {
            "id": a.id,
            "task_id": a.task_id,
            "task_name": a.task.name if a.task else "",
            "alarm_type": a.alarm_type,
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "detected_behaviors": a.detected_behaviors,
            "confidence": a.confidence,
            "status": a.status,
            "reviewer_note": a.reviewer_note,
            "created_at": a.created_at.isoformat(),
            "image_url": get_presigned_url(a.image_object_name) if a.image_object_name else None,
            "video_url": get_presigned_url(a.video_object_name) if a.video_object_name else None,
            "audio_url": get_presigned_url(a.audio_object_name) if a.audio_object_name else None,
        }
        items.append(item)

    return jsonify({
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
        "items": items,
    })


@api_bp.route("/alarms/<int:alarm_id>/review", methods=["POST"])
def review_alarm(alarm_id):
    alarm = AlarmRecord.query.get_or_404(alarm_id)
    data = request.get_json(silent=True) or {}
    valid_statuses = {"confirmed", "false_alarm", "handled", "pending"}
    new_status = data.get("status", "handled")
    if new_status not in valid_statuses:
        return _error(f"无效状态: {new_status}")
    alarm.status = new_status
    alarm.reviewer_note = str(data.get("note", ""))[:1000]
    alarm.reviewed_at = datetime.now()
    db.session.commit()
    return jsonify({"message": "复核成功"})


@api_bp.route("/alarms/<int:alarm_id>", methods=["GET"])
def get_alarm_detail(alarm_id):
    a = AlarmRecord.query.get_or_404(alarm_id)
    return jsonify({
        "id": a.id,
        "task_name": a.task.name if a.task else "",
        "alarm_type": a.alarm_type,
        "severity": a.severity,
        "title": a.title,
        "description": a.description,
        "detected_behaviors": a.detected_behaviors,
        "violated_rules": a.violated_rules,
        "detected_objects": a.detected_objects,
        "confidence": a.confidence,
        "vlm_raw_response": a.vlm_raw_response,
        "status": a.status,
        "reviewer_note": a.reviewer_note,
        "created_at": a.created_at.isoformat(),
        "image_url": get_presigned_url(a.image_object_name) if a.image_object_name else None,
    })


@api_bp.route("/metrics/snapshot", methods=["GET"])
def metrics_snapshot():
    from core.redis_client import get_queue_size
    return jsonify({
        "vlm_queue_size": get_queue_size(settings.queue.vlm_task_queue),
        "alarm_queue_size": get_queue_size(settings.queue.alarm_save_queue),
        "timestamp": datetime.now().isoformat(),
    })


@api_bp.errorhandler(400)
def bad_request(e):
    return _error("请求参数错误")


@api_bp.errorhandler(404)
def not_found(e):
    return _error("资源不存在", 404)


@api_bp.errorhandler(500)
def internal_error(e):
    return _error("服务器内部错误", 500)
