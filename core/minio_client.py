import io
from datetime import timedelta
from typing import Optional, List
from minio import Minio
from minio.error import S3Error
from config.settings import get_settings
from core.logger import get_logger

logger = get_logger(__name__)

_minio_client: Optional[Minio] = None


def get_minio() -> Minio:
    global _minio_client
    if _minio_client is None:
        settings = get_settings()
        _minio_client = Minio(
            settings.minio.endpoint,
            access_key=settings.minio.access_key,
            secret_key=settings.minio.secret_key,
            secure=settings.minio.secure,
        )
        bucket = settings.minio.bucket
        if not _minio_client.bucket_exists(bucket):
            _minio_client.make_bucket(bucket)
            logger.info("minio_bucket_created", bucket=bucket)
        logger.info("minio_connected", endpoint=settings.minio.endpoint, bucket=bucket)
    return _minio_client


def upload_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
    try:
        settings = get_settings()
        client = get_minio()
        client.put_object(
            settings.minio.bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        logger.debug("minio_uploaded", object=object_name, size=len(data))
        return object_name
    except S3Error as e:
        logger.error("minio_upload_failed", object=object_name, error=str(e))
        return None


def upload_file(object_name: str, file_path: str, content_type: str = "application/octet-stream") -> Optional[str]:
    try:
        settings = get_settings()
        client = get_minio()
        client.fput_object(settings.minio.bucket, object_name, file_path, content_type=content_type)
        logger.debug("minio_uploaded_file", object=object_name, path=file_path)
        return object_name
    except S3Error as e:
        logger.error("minio_upload_file_failed", object=object_name, error=str(e))
        return None


def get_presigned_url(object_name: str, expires_days: int = 7) -> Optional[str]:
    try:
        settings = get_settings()
        client = get_minio()
        url = client.presigned_get_object(
            settings.minio.bucket, object_name,
            expires=timedelta(days=expires_days)
        )
        return url
    except S3Error as e:
        logger.error("minio_presign_failed", object=object_name, error=str(e))
        return None


def object_exists(object_name: str) -> bool:
    try:
        settings = get_settings()
        client = get_minio()
        client.stat_object(settings.minio.bucket, object_name)
        return True
    except S3Error:
        return False


VIDEO_BUCKET = "videos"


def ensure_video_bucket() -> str:
    """Ensure the videos bucket exists and return its name."""
    client = get_minio()
    if not client.bucket_exists(VIDEO_BUCKET):
        client.make_bucket(VIDEO_BUCKET)
        logger.info("minio_video_bucket_created", bucket=VIDEO_BUCKET)
    return VIDEO_BUCKET


def upload_file_to_videos(object_name: str, file_path: str, content_type: str = "video/mp4") -> Optional[str]:
    """Upload a local file to the videos bucket. Returns object_name on success."""
    try:
        client = get_minio()
        bucket = ensure_video_bucket()
        client.fput_object(bucket, object_name, file_path, content_type=content_type)
        logger.info("minio_video_uploaded", object=object_name, path=file_path)
        return object_name
    except S3Error as e:
        logger.error("minio_video_upload_failed", object=object_name, error=str(e))
        return None


def download_file_from_videos(object_name: str, dest_path: str) -> bool:
    """Download a file from the videos bucket to a local path."""
    try:
        client = get_minio()
        client.fget_object(VIDEO_BUCKET, object_name, dest_path)
        logger.debug("minio_video_downloaded", object=object_name, dest=dest_path)
        return True
    except S3Error as e:
        logger.error("minio_video_download_failed", object=object_name, error=str(e))
        return False


def get_video_presigned_url(object_name: str, expires_days: int = 1) -> Optional[str]:
    """Get a presigned URL for a video object."""
    try:
        client = get_minio()
        url = client.presigned_get_object(
            VIDEO_BUCKET, object_name,
            expires=timedelta(days=expires_days)
        )
        return url
    except S3Error as e:
        logger.error("minio_video_presign_failed", object=object_name, error=str(e))
        return None


def remove_object(bucket: str, object_name: str) -> bool:
    """Remove a single object from a bucket."""
    try:
        client = get_minio()
        client.remove_object(bucket, object_name)
        logger.debug("minio_object_removed", bucket=bucket, object=object_name)
        return True
    except S3Error as e:
        logger.error("minio_object_remove_failed", bucket=bucket, object=object_name, error=str(e))
        return False


def remove_objects(bucket: str, object_names: List[str]) -> bool:
    """Remove multiple objects from a bucket."""
    try:
        client = get_minio()
        errors = client.remove_objects(bucket, object_names)
        for err in errors:
            logger.error("minio_batch_remove_error", bucket=bucket, error=str(err))
        logger.debug("minio_objects_removed", bucket=bucket, count=len(object_names))
        return True
    except S3Error as e:
        logger.error("minio_batch_remove_failed", bucket=bucket, error=str(e))
        return False


def list_objects(bucket: str, prefix: str = "", recursive: bool = True) -> List[str]:
    """List object names in a bucket with optional prefix."""
    try:
        client = get_minio()
        return [obj.object_name for obj in client.list_objects(bucket, prefix=prefix, recursive=recursive)]
    except S3Error as e:
        logger.error("minio_list_failed", bucket=bucket, error=str(e))
        return []
