from time import sleep

import cv2
from flask import Blueprint, Response, current_app, stream_with_context

from core.task_service import get_task
from web.routes.response import error_response, success_response


runtime_bp = Blueprint("runtime", __name__, url_prefix="/api/analysis-tasks")


def _manager():
    return current_app.extensions["runtime_manager"]


@runtime_bp.route("/<int:task_id>/runtime", methods=["GET"])
def runtime_status(task_id: int):
    if get_task(task_id) is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)
    status = _manager().status(task_id)
    if status is None:
        return error_response(
            "RUNTIME_NOT_STARTED",
            "Task runtime has not been started",
            status_code=409,
        )
    return success_response(status)


@runtime_bp.route("/<int:task_id>/preview", methods=["GET"])
def runtime_preview(task_id: int):
    if get_task(task_id) is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)
    if _manager().status(task_id) is None:
        return error_response(
            "RUNTIME_NOT_STARTED",
            "Task runtime has not been started",
            status_code=409,
        )

    def generate():
        last_frame_index = None
        while True:
            packet = _manager().latest_frame(task_id)
            if packet is None or packet.frame_index == last_frame_index:
                sleep(0.05)
                continue
            ok, encoded = cv2.imencode(".jpg", packet.frame)
            if not ok:
                sleep(0.05)
                continue
            last_frame_index = packet.frame_index
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + encoded.tobytes()
                + b"\r\n"
            )

    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@runtime_bp.route("/<int:task_id>/detection-preview", methods=["GET"])
def detection_preview(task_id: int):
    if get_task(task_id) is None:
        return error_response("TASK_NOT_FOUND", "Task not found", status_code=404)
    if _manager().status(task_id) is None:
        return error_response(
            "RUNTIME_NOT_STARTED",
            "Task runtime has not been started",
            status_code=409,
        )

    def generate():
        last_frame_index = None
        while True:
            result = _manager().latest_detection(task_id)
            if result is None or result.packet.frame_index == last_frame_index:
                sleep(0.05)
                continue
            ok, encoded = cv2.imencode(".jpg", result.annotated_frame)
            if not ok:
                sleep(0.05)
                continue
            last_frame_index = result.packet.frame_index
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + encoded.tobytes()
                + b"\r\n"
            )

    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
