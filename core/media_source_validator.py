import os
import re
import json
import time
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from config.settings import get_settings, PROJECT_ROOT
from core.logger import get_logger

logger = get_logger(__name__)

# MediaMTX RTSP path pattern: /<name>
MEDIAMTX_PATH_RE = re.compile(r'^/[a-zA-Z0-9_.-]+$')


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    latency_ms: float
    format_name: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def normalize_uri(uri: str) -> dict:
    """
    Normalize a media URI and determine its type.

    Returns:
        dict with keys: normalized (str or None), source_type (str or None), error (str or None)
    """
    if not uri or not uri.strip():
        return {"normalized": None, "source_type": None, "error": "URI is empty"}

    uri = uri.strip()
    uri_lower = uri.lower()

    if uri_lower.startswith("rtsp://"):
        return {"normalized": uri, "source_type": "rtsp", "error": None}
    elif uri_lower.startswith("rtmp://"):
        return {"normalized": uri, "source_type": "rtmp", "error": None}
    elif uri_lower.startswith("http://") or uri_lower.startswith("https://"):
        return {"normalized": uri, "source_type": "http", "error": None}
    elif "/" in uri or "\\\\" in uri or "." in uri:
        p = Path(uri)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return {"normalized": str(p.resolve()), "source_type": "local_file", "error": None}
    else:
        return {"normalized": None, "source_type": None, "error": f"Unrecognized URI format: {uri}"}


def is_path_safe(path: str) -> bool:
    """
    Check if a file path is safe to access.
    - Rejects paths with traversal sequences (../, ..\\)
    - Rejects paths with null bytes or encoded null bytes
    - Rejects absolute paths outside the allowed directory
    """
    if not path:
        return False

    if "\\x00" in path or "%00" in path:
        return False

    # Normalize backslashes to forward slashes for consistent checking
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        return False

    settings = get_settings()
    allowed_dirs = [PROJECT_ROOT]
    if settings.media and hasattr(settings.media, "allowed_dirs"):
        for d in settings.media.allowed_dirs:
            allowed_dirs.append(Path(d).resolve())

    try:
        p = Path(path)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        else:
            p = p.resolve()

        for allowed in allowed_dirs:
            try:
                p.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False
    except (ValueError, RuntimeError, OSError):
        return False


def sanitize_credentials(uri: Optional[str]) -> str:
    if not uri:
        return ""

    try:
        parsed = urlparse(uri)
        if parsed.username or parsed.password:
            if parsed.password:
                netloc = f"{parsed.username}:****@{parsed.hostname}"
            else:
                netloc = f"{parsed.username}@{parsed.hostname}"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            sanitized = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
            return sanitized
        return uri
    except Exception:
        return uri


def log_safe_url(uri: Optional[str]) -> str:
    if not uri:
        return ""

    try:
        parsed = urlparse(uri)
        if parsed.username or parsed.password:
            netloc = f"****:****@{parsed.hostname}"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            sanitized = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
            return sanitized
        return uri
    except Exception:
        return uri


def probe_media(path: str) -> ProbeResult:
    start = time.monotonic()
    try:
        if not path.startswith("rtsp://") and not path.startswith("rtmp://") and not path.startswith("http"):
            p = Path(path)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if not p.exists():
                elapsed = (time.monotonic() - start) * 1000
                return ProbeResult(
                    ok=False,
                    latency_ms=elapsed,
                    error_code="FILE_NOT_FOUND",
                    error_message=f"File not found: {path}",
                )

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        elapsed = (time.monotonic() - start) * 1000

        if result.returncode != 0:
            return ProbeResult(
                ok=False,
                latency_ms=elapsed,
                error_code="FFPROBE_FAILED",
                error_message=result.stderr.strip() or "ffprobe returned non-zero exit code",
            )

        data = json.loads(result.stdout)
        width = None
        height = None
        fps = None
        format_name = None

        if "format" in data:
            format_name = data["format"].get("format_name", "")

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                fps_str = stream.get("r_frame_rate", "0/1")
                try:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den) if float(den) > 0 else None
                except (ValueError, ZeroDivisionError):
                    fps = None
                break

        return ProbeResult(
            ok=True,
            latency_ms=elapsed,
            format_name=format_name,
            width=width,
            height=height,
            fps=fps,
            error_code=None,
            error_message=None,
        )

    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return ProbeResult(
            ok=False,
            latency_ms=elapsed,
            error_code="PROBE_TIMEOUT",
            error_message="FFprobe timed out after 15 seconds",
        )
    except FileNotFoundError:
        elapsed = (time.monotonic() - start) * 1000
        return ProbeResult(
            ok=False,
            latency_ms=elapsed,
            error_code="FFPROBE_NOT_FOUND",
            error_message="FFprobe is not installed or not in PATH",
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return ProbeResult(
            ok=False,
            latency_ms=elapsed,
            error_code="PROBE_ERROR",
            error_message=str(e),
        )
