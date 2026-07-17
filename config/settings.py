import os
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class YoloConfig(BaseModel):
    model: str = "yolov8s.pt"
    device: str = "cuda"
    confidence: float = 0.5
    iou_threshold: float = 0.45
    batch_size: int = 1
    half: bool = True
    onnx: bool = False


class VlmConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    max_tokens: int = 1024
    temperature: float = 0.1
    timeout: int = 30
    max_retries: int = 2
    enable_cache: bool = True
    cache_ttl: int = 300
    cache_similarity_threshold: int = 5


class MysqlConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3307
    user: str = "root"
    password: str = ""
    database: str = "video_analyzer"


class RedisConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class MinioConfig(BaseModel):
    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin123"
    bucket: str = "alarm-media"
    secure: bool = False


class MediaMTXConfig(BaseModel):
    rtsp_url: str = "rtsp://127.0.0.1:8554"
    webrtc_port: int = 8889
    hls_port: int = 8888


class QueueConfig(BaseModel):
    vlm_task_queue: str = "vlm:tasks"
    audio_task_queue: str = "audio:tasks"
    alarm_save_queue: str = "alarm:save"
    result_prefix: str = "result:"
    result_ttl: int = 3600


class AnalysisConfig(BaseModel):
    mode: str = "small_crop"
    vlm_interval: float = 2.0
    temporal_window: float = 5.0
    temporal_frames: int = 8


class AudioConfig(BaseModel):
    enabled: bool = True
    sample_rate: int = 16000
    chunk_duration: float = 5.0
    abnormal_threshold: float = 0.6
    vlm_confirm: bool = True


class ChromaConfig(BaseModel):
    persist_path: str = "./data/vectors"
    collection_name: str = "safety_rules"
    embedding_model: str = "all-MiniLM-L6-v2"


class ObservabilityConfig(BaseModel):
    log_level: str = "INFO"
    metrics_enabled: bool = True
    dashboard_refresh: int = 5
    perf_collect_interval: int = 5


class StorageConfig(BaseModel):
    keep_days: int = 30
    alarm_image_path: str = "alarms/images"
    alarm_video_path: str = "alarms/videos"
    alarm_audio_path: str = "alarms/audio"


class FlaskConfig(BaseModel):
    env: str = "development"
    port: int = 8080
    secret_key: str = "dev-secret"


class Settings(BaseModel):
    flask: FlaskConfig = Field(default_factory=FlaskConfig)
    mysql: MysqlConfig = Field(default_factory=MysqlConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    minio: MinioConfig = Field(default_factory=MinioConfig)
    mediamtx: MediaMTXConfig = Field(default_factory=MediaMTXConfig)
    yolo: YoloConfig = Field(default_factory=YoloConfig)
    vlm: VlmConfig = Field(default_factory=VlmConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


_settings: Optional[Settings] = None


def _load_yaml() -> dict:
    yaml_path = PROJECT_ROOT / "config" / "default.yaml"
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        yaml_cfg = _load_yaml()

        _settings = Settings(
            flask=FlaskConfig(
                env=os.getenv("FLASK_ENV", yaml_cfg.get("flask", {}).get("env", "development")),
                port=int(os.getenv("FLASK_PORT", str(yaml_cfg.get("flask", {}).get("port", 8080)))),
                secret_key=os.getenv("SECRET_KEY", yaml_cfg.get("flask", {}).get("secret_key", "dev-secret")),
            ),
            mysql=MysqlConfig(
                host=os.getenv("MYSQL_HOST", yaml_cfg.get("mysql", {}).get("host", "127.0.0.1")),
                port=int(os.getenv("MYSQL_PORT", str(yaml_cfg.get("mysql", {}).get("port", 3307)))),
                user=os.getenv("MYSQL_USER", yaml_cfg.get("mysql", {}).get("user", "root")),
                password=os.getenv("MYSQL_PASSWORD", yaml_cfg.get("mysql", {}).get("password", "")),
                database=os.getenv("MYSQL_DATABASE", yaml_cfg.get("mysql", {}).get("database", "video_analyzer")),
            ),
            redis=RedisConfig(
                host=os.getenv("REDIS_HOST", yaml_cfg.get("redis", {}).get("host", "127.0.0.1")),
                port=int(os.getenv("REDIS_PORT", str(yaml_cfg.get("redis", {}).get("port", 6379)))),
                db=int(os.getenv("REDIS_DB", str(yaml_cfg.get("redis", {}).get("db", 0)))),
                password=os.getenv("REDIS_PASSWORD") or yaml_cfg.get("redis", {}).get("password"),
            ),
            minio=MinioConfig(
                endpoint=os.getenv("MINIO_ENDPOINT", yaml_cfg.get("minio", {}).get("endpoint", "127.0.0.1:9000")),
                access_key=os.getenv("MINIO_ACCESS_KEY", yaml_cfg.get("minio", {}).get("access_key", "minioadmin")),
                secret_key=os.getenv("MINIO_SECRET_KEY", yaml_cfg.get("minio", {}).get("secret_key", "minioadmin123")),
                bucket=os.getenv("MINIO_BUCKET", yaml_cfg.get("minio", {}).get("bucket", "alarm-media")),
                secure=os.getenv("MINIO_SECURE", str(yaml_cfg.get("minio", {}).get("secure", "false"))).lower() == "true",
            ),
            mediamtx=MediaMTXConfig(
                rtsp_url=os.getenv("MEDIAMTX_RTSP_URL", yaml_cfg.get("mediamtx", {}).get("rtsp_url", "rtsp://127.0.0.1:8554")),
                webrtc_port=int(os.getenv("MEDIAMTX_WEBRTC_PORT", str(yaml_cfg.get("mediamtx", {}).get("webrtc_port", 8889)))),
                hls_port=int(os.getenv("MEDIAMTX_HLS_PORT", str(yaml_cfg.get("mediamtx", {}).get("hls_port", 8888)))),
            ),
            yolo=YoloConfig(**yaml_cfg.get("yolo", {})),
            vlm=VlmConfig(**yaml_cfg.get("vlm", {})),
            queue=QueueConfig(**yaml_cfg.get("queue", {})),
            analysis=AnalysisConfig(**yaml_cfg.get("analysis", {})),
            audio=AudioConfig(**yaml_cfg.get("audio", {})),
            chroma=ChromaConfig(**yaml_cfg.get("chroma", {})),
            observability=ObservabilityConfig(**yaml_cfg.get("observability", {})),
            storage=StorageConfig(**yaml_cfg.get("storage", {})),
        )

        # VLM API Key 从环境变量覆盖
        if os.getenv("VLM_API_KEY"):
            _settings.vlm.api_key = os.getenv("VLM_API_KEY")
        if os.getenv("VLM_BASE_URL"):
            _settings.vlm.base_url = os.getenv("VLM_BASE_URL")
        if os.getenv("VLM_MODEL"):
            _settings.vlm.model = os.getenv("VLM_MODEL")
        # YOLO device 环境变量覆盖
        if os.getenv("YOLO_DEVICE"):
            _settings.yolo.device = os.getenv("YOLO_DEVICE")
        if os.getenv("YOLO_MODEL"):
            _settings.yolo.model = os.getenv("YOLO_MODEL")

    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()
