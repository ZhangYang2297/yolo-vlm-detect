from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from core.db import db


class VideoSource(db.Model):
    __tablename__ = "video_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment="\u89c6\u9891\u6e90\u540d\u79f0")
    source_type = Column(String(20), nullable=False, comment="local_file/rtsp/rtmp/http")
    url = Column(String(500), nullable=False, comment="\u89c6\u9891\u6e90\u5730\u5740/\u8def\u5f84")
    storage_uri = Column(String(500), default="", comment="MinIO object URI, e.g. videos/xxx.mp4")
    media_mtx_path = Column(String(100), default="", comment="MediaMTX\u63a8\u6d41\u8def\u5f84")
    connection_status = Column(String(20), default="unknown", comment="unknown/checking/online/offline")
    last_probe_at = Column(DateTime, nullable=True, comment="\u4e0a\u6b21\u63a2\u6d4b\u65f6\u95f4")
    last_probe_ok = Column(Boolean, nullable=True, comment="\u4e0a\u6b21\u63a2\u6d4b\u662f\u5426\u6210\u529f")
    format_name = Column(String(50), default="", comment="\u5c01\u88c5\u683c\u5f0f")
    width = Column(Integer, nullable=True, comment="\u89c6\u9891\u5bbd\u5ea6")
    height = Column(Integer, nullable=True, comment="\u89c6\u9891\u9ad8\u5ea6")
    fps = Column(Float, nullable=True, comment="\u5e27\u7387")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    tasks = relationship("AnalysisTask", back_populates="video_source", foreign_keys="AnalysisTask.source_id")


class AnalysisTask(db.Model):
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="\u4efb\u52a1\u540d\u79f0")
    source_url = Column(String(500), nullable=False, comment="\u89c6\u9891\u6e90\u5730\u5740/\u8def\u5f84")
    source_type = Column(String(20), default="video", comment="video/camera/stream")
    source_id = Column(Integer, ForeignKey("video_sources.id", ondelete="SET NULL"), nullable=True, index=True, comment="\u5f15\u7528VideoSource")
    enabled = Column(Boolean, default=True)
    detect_classes = Column(JSON, default=lambda: ["person"], comment="YOLO\u68c0\u6d4b\u7c7b\u522b\u5217\u8868")
    target_actions = Column(JSON, default=lambda: [], comment="\u5f85\u68c0\u6d4b\u884c\u4e3a\u5217\u8868\uff0c\u7a7a=\u5de1\u68c0\u6a21\u5f0f")
    scene_description = Column(Text, default="", comment="\u573a\u666f\u63cf\u8ff0")
    rule_doc_ids = Column(JSON, default=lambda: [], comment="\u7ed1\u5b9a\u7684\u89c4\u8303\u6587\u6863ID")
    roi_points = Column(JSON, default=lambda: [], comment="ROI\u533a\u57df\u591a\u8fb9\u5f62\u9876\u70b9")
    audio_enabled = Column(Boolean, default=True, comment="\u542f\u7528\u97f3\u9891\u5206\u6790")
    record_video = Column(Boolean, default=False, comment="\u544a\u8b66\u65f6\u5f55\u50cf")
    vlm_mode = Column(String(20), default="small_crop", comment="\u5206\u6790\u6a21\u5f0f")
    stream_path = Column(String(100), default="", comment="MediaMTX\u63a8\u6d41\u8def\u5f84")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    alarms = relationship("AlarmRecord", back_populates="task", cascade="all, delete-orphan")
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")
    video_source = relationship("VideoSource", back_populates="tasks", foreign_keys=[source_id])


class TaskRun(db.Model):
    __tablename__ = "task_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="\u5bf9\u5e94\u4efb\u52a1ID")
    status = Column(String(20), default="created", index=True, comment="created/starting/running/stopping/stopped/failed")
    config_snapshot = Column(JSON, nullable=False, comment="\u542f\u52a8\u65f6\u7684\u914d\u7f6e\u5feb\u7167")
    error_message = Column(Text, default="", comment="\u5931\u8d25\u539f\u56e0")
    started_at = Column(DateTime, nullable=True, comment="\u5f00\u59cb\u65f6\u95f4")
    stopped_at = Column(DateTime, nullable=True, comment="\u7ed3\u675f\u65f6\u95f4")
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("AnalysisTask", back_populates="runs")


class AlarmRecord(db.Model):
    __tablename__ = "alarm_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    alarm_type = Column(String(20), nullable=False, comment="video/audio/system")
    severity = Column(String(20), default="warning", comment="info/warning/critical")
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    detected_behaviors = Column(JSON, default=lambda: [])
    violated_rules = Column(JSON, default=lambda: [])
    detected_objects = Column(JSON, default=lambda: [])
    confidence = Column(Float, default=0.0)
    image_object_name = Column(String(500), default="", comment="MinIO\u4e2d\u622a\u56fe\u5bf9\u8c61\u540d")
    video_object_name = Column(String(500), default="", comment="MinIO\u4e2d\u5f55\u50cf\u5bf9\u8c61\u540d")
    audio_object_name = Column(String(500), default="", comment="MinIO\u4e2d\u97f3\u9891\u5bf9\u8c61\u540d")
    vlm_raw_response = Column(Text, default="")
    vlm_thinking = Column(Text, default="")
    status = Column(String(20), default="pending", index=True, comment="pending/confirmed/false_alarm/handled")
    reviewer_note = Column(Text, default="")
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    task = relationship("AnalysisTask", back_populates="alarms")


class RuleDocument(db.Model):
    __tablename__ = "rule_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    file_object_name = Column(String(500), nullable=False, comment="PDF\u5728MinIO\u4e2d\u7684\u5bf9\u8c61\u540d")
    file_md5 = Column(String(32), unique=True)
    chunk_count = Column(Integer, default=0)
    rule_count = Column(Integer, default=0)
    status = Column(String(20), default="pending", comment="pending/processing/completed/failed")
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    rules = relationship("ExtractedRule", back_populates="document", cascade="all, delete-orphan")


class ExtractedRule(db.Model):
    __tablename__ = "extracted_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("rule_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_number = Column(String(50), default="")
    title = Column(String(200), default="")
    violation_desc = Column(Text, default="")
    visual_features = Column(Text, default="")
    detection_suggestion = Column(Text, default="")
    enabled = Column(Boolean, default=True, index=True)
    chroma_id = Column(String(100), default="", comment="Chroma\u5411\u91cfID")
    created_at = Column(DateTime, default=datetime.now)

    document = relationship("RuleDocument", back_populates="rules")


class SystemMetric(db.Model):
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_time = Column(DateTime, default=datetime.now, index=True)
    yolo_fps = Column(Float, default=0.0)
    vlm_qps = Column(Float, default=0.0)
    queue_size = Column(Integer, default=0)
    gpu_util = Column(Float, default=0.0)
    gpu_memory_mb = Column(Float, default=0.0)
    cpu_percent = Column(Float, default=0.0)
    memory_percent = Column(Float, default=0.0)
