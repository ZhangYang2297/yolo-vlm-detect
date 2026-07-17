import io
from datetime import timedelta
from typing import Optional
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
