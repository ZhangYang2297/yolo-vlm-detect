from flask import Blueprint, render_template
from core.db import db
from core.models import AnalysisTask

monitor_views_bp = Blueprint("monitor_views", __name__)


@monitor_views_bp.route("/monitor")
def monitor():
    return render_template("monitor/index.html")


@monitor_views_bp.route("/monitor/<int:task_id>")
def monitor_task(task_id: int):
    task = db.session.get(AnalysisTask, task_id)
    if task is None:
        return "Task not found", 404
    return render_template("monitor/index.html", task=task)


@monitor_views_bp.route("/history")
def history():
    return render_template("monitor/history.html")


@monitor_views_bp.route("/alerts-center")
def alerts_center():
    return render_template("monitor/alerts.html")


@monitor_views_bp.route("/settings")
def settings_page():
    return render_template("monitor/settings.html")
