from flask import Blueprint, render_template, jsonify
from sqlalchemy import func
from core.db import db
from core.models import AnalysisTask, AlarmRecord, RuleDocument

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def dashboard():
    active_tasks = AnalysisTask.query.filter_by(enabled=True).count()
    total_tasks = AnalysisTask.query.count()
    total_alarms = AlarmRecord.query.count()
    today_alarms = AlarmRecord.query.filter(
        func.date(AlarmRecord.created_at) == func.current_date()
    ).count()
    pending_alarms = AlarmRecord.query.filter_by(status="pending").count()
    return render_template(
        "dashboard.html",
        active_tasks=active_tasks,
        total_tasks=total_tasks,
        total_alarms=total_alarms,
        today_alarms=today_alarms,
        pending_alarms=pending_alarms,
    )


@views_bp.route("/tasks")
def tasks():
    return render_template("tasks.html")


@views_bp.route("/alarms")
def alarms():
    return render_template("alarms.html")


@views_bp.route("/rules")
def rules():
    return render_template("rules.html")


@views_bp.route("/live/<int:task_id>")
def live_detection(task_id: int):
    task = db.session.get(AnalysisTask, task_id)
    if task is None:
        return "Task not found", 404
    return render_template("live_detection.html", task=task)
