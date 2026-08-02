from datetime import datetime
from typing import Optional, List
from sqlalchemy.exc import IntegrityError
from core.db import db
from core.models import VideoSource, AnalysisTask
from core.media_source_validator import normalize_uri, sanitize_credentials, probe_media, is_path_safe
from core.logger import get_logger

logger = get_logger(__name__)


class VideoSourceError(Exception):
    pass


class VideoSourceNotFoundError(VideoSourceError):
    def __init__(self, source_id: int):
        self.source_id = source_id
        super().__init__(f"VideoSource {source_id} not found")


class VideoSourceConflictError(VideoSourceError):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"VideoSource with name '{name}' already exists")


class VideoSourceURIError(VideoSourceError):
    def __init__(self, message: str):
        super().__init__(message)


def create_video_source(data: dict) -> VideoSource:
    """Create a new video source with validation."""
    name = data.get("name", "").strip()
    if not name:
        raise VideoSourceURIError("name is required")

    source_type = data.get("source_type", "").strip()
    url = data.get("url", "").strip()

    if not source_type:
        raise VideoSourceURIError("source_type is required")
    if not url:
        raise VideoSourceURIError("url is required")

    # Validate URI
    uri_result = normalize_uri(url)
    if uri_result.get("error") and source_type == "local_file" and not url.startswith("rtsp") and not url.startswith("rtmp") and not url.startswith("http"):
        raise VideoSourceURIError(uri_result["error"])

    # Check path safety for local files
    if source_type == "local_file" and not is_path_safe(url):
        raise VideoSourceURIError("Path is not safe or outside allowed directories")

    vs = VideoSource(
        name=name,
        source_type=source_type,
        url=url,
        media_mtx_path=data.get("media_mtx_path", ""),
        connection_status="unknown",
        enabled=data.get("enabled", True),
    )
    db.session.add(vs)
    try:
        db.session.commit()
        logger.info("video_source_created", source_id=vs.id, name=name, source_type=source_type)
        return vs
    except IntegrityError:
        db.session.rollback()
        raise VideoSourceConflictError(name)


def get_video_source(source_id: int) -> Optional[VideoSource]:
    """Get a video source by ID."""
    return db.session.get(VideoSource, source_id)


def update_video_source(source_id: int, data: dict) -> VideoSource:
    """Update a video source."""
    vs = get_video_source(source_id)
    if vs is None:
        raise VideoSourceNotFoundError(source_id)

    if "name" in data:
        name = data["name"].strip()
        if name:
            vs.name = name
    if "source_type" in data:
        vs.source_type = data["source_type"]
    if "url" in data:
        vs.url = data["url"]
    if "media_mtx_path" in data:
        vs.media_mtx_path = data["media_mtx_path"]
    if "enabled" in data:
        vs.enabled = data["enabled"]

    try:
        db.session.commit()
        logger.info("video_source_updated", source_id=source_id)
        return vs
    except IntegrityError:
        db.session.rollback()
        raise VideoSourceConflictError(vs.name)


def delete_video_source(source_id: int) -> None:
    """Delete a video source."""
    vs = get_video_source(source_id)
    if vs is None:
        raise VideoSourceNotFoundError(source_id)

    db.session.delete(vs)
    db.session.commit()
    logger.info("video_source_deleted", source_id=source_id)


def list_video_sources(enabled_only: bool = False) -> List[VideoSource]:
    """List all video sources."""
    query = VideoSource.query.order_by(VideoSource.created_at.desc())
    if enabled_only:
        query = query.filter(VideoSource.enabled.is_(True))
    return query.all()


def probe_video_source(source_id: int) -> dict:
    """Probe a video source to check connectivity."""
    vs = get_video_source(source_id)
    if vs is None:
        raise VideoSourceNotFoundError(source_id)

    result = probe_media(vs.url)

    if result.ok:
        vs.connection_status = "online"
        vs.last_probe_ok = True
        vs.format_name = result.format_name or ""
        vs.width = result.width
        vs.height = result.height
        vs.fps = result.fps
    else:
        vs.connection_status = "offline"
        vs.last_probe_ok = False

    vs.last_probe_at = datetime.now()
    db.session.commit()

    logger.info("video_source_probed", source_id=source_id, ok=result.ok, latency_ms=result.latency_ms)

    return {
        "ok": result.ok,
        "latency_ms": result.latency_ms,
        "format_name": result.format_name,
        "width": result.width,
        "height": result.height,
        "fps": result.fps,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }
