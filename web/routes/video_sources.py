from flask import Blueprint, request, jsonify
from web.routes.response import success_response, error_response
from core.video_source_service import (
    create_video_source, get_video_source, update_video_source,
    delete_video_source, list_video_sources, probe_video_source,
    VideoSourceNotFoundError, VideoSourceConflictError, VideoSourceURIError,
)
from core.media_source_validator import sanitize_credentials

video_sources_bp = Blueprint("video_sources", __name__, url_prefix="/api/video-sources")


@video_sources_bp.route("", methods=["GET"])
def list_sources():
    enabled_only = request.args.get("enabled_only", "false").lower() == "true"
    sources = list_video_sources(enabled_only=enabled_only)
    return success_response([{
        "id": s.id,
        "name": s.name,
        "source_type": s.source_type,
        "url": sanitize_credentials(s.url),
        "media_mtx_path": s.media_mtx_path,
        "connection_status": s.connection_status,
        "enabled": s.enabled,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    } for s in sources])


@video_sources_bp.route("", methods=["POST"])
def create_source():
    data = request.get_json(silent=True)
    if not data:
        return error_response("INVALID_JSON", "Request body must be valid JSON")
    try:
        vs = create_video_source(data)
        return success_response({
            "id": vs.id,
            "name": vs.name,
            "source_type": vs.source_type,
            "url": sanitize_credentials(vs.url),
            "media_mtx_path": vs.media_mtx_path,
            "connection_status": vs.connection_status,
            "enabled": vs.enabled,
        }, status_code=201)
    except VideoSourceURIError as e:
        return error_response("INVALID_URI", str(e))
    except VideoSourceConflictError as e:
        return error_response("CONFLICT", str(e), status_code=409)


@video_sources_bp.route("/<int:source_id>", methods=["GET"])
def get_source(source_id: int):
    vs = get_video_source(source_id)
    if vs is None:
        return error_response("SOURCE_NOT_FOUND", "Video source not found", status_code=404)
    return success_response({
        "id": vs.id,
        "name": vs.name,
        "source_type": vs.source_type,
        "url": sanitize_credentials(vs.url),
        "media_mtx_path": vs.media_mtx_path,
        "connection_status": vs.connection_status,
        "last_probe_at": vs.last_probe_at.isoformat() if vs.last_probe_at else None,
        "last_probe_ok": vs.last_probe_ok,
        "format_name": vs.format_name,
        "width": vs.width,
        "height": vs.height,
        "fps": vs.fps,
        "enabled": vs.enabled,
        "created_at": vs.created_at.isoformat() if vs.created_at else None,
        "updated_at": vs.updated_at.isoformat() if vs.updated_at else None,
    })


@video_sources_bp.route("/<int:source_id>", methods=["DELETE"])
def delete_source(source_id: int):
    try:
        delete_video_source(source_id)
        return success_response({"deleted": True})
    except VideoSourceNotFoundError:
        return error_response("SOURCE_NOT_FOUND", "Video source not found", status_code=404)


@video_sources_bp.route("/<int:source_id>/probe", methods=["POST"])
def probe_source(source_id: int):
    try:
        result = probe_video_source(source_id)
        return success_response(result)
    except VideoSourceNotFoundError:
        return error_response("SOURCE_NOT_FOUND", "Video source not found", status_code=404)
