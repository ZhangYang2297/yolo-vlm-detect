from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from core.db import db


class AnalysisTask(db.Model):
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="任务名称")
    source_url = Column(String(500), nullable=False, comment="视频源地址/路径")
    source_type = Column(String(20), default="video", comment="video/camera/stream")
    enabled = Column(Boolean, default=True)
    detect_classes = Column(JSON, default=["person"], comment="YOLO检测类别列表")
    target_actions = Column(JSON, default=[], comment="待检测行为列表，空=巡检模式")
    scene_description = Column(Text, default="", comment="场景描述")
    rule_doc_ids = Column(JSON, default=[], comment="绑定的规范文档ID")
    roi_points = Column(JSON, default=[], comment="ROI区域多边形顶点")
    audio_enabled = Column(Boolean, default=True, comment="启用音频分析")
    record_video = Column(Boolean, default=False, comment="告警时录像")
    vlm_mode = Column(String(20), default="small_crop", comment="分析模式")
    stream_path = Column(String(100), default="", comment="MediaMTX推流路径")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    alarms = relationship("AlarmRecord", back_populates="task", cascade="all, delete-orphan")


class AlarmRecord(db.Model):
    __tablename__ = "alarm_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    alarm_type = Column(String(20), nullable=False, comment="video/audio/system")
    severity = Column(String(20), default="warning", comment="info/warning/critical")
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    detected_behaviors = Column(JSON, default=[])
    violated_rules = Column(JSON, default=[])
    detected_objects = Column(JSON, default=[])
    confidence = Column(Float, default=0.0)
    image_object_name = Column(String(500), default="", comment="MinIO中截图对象名")
    video_object_name = Column(String(500), default="", comment="MinIO中录像对象名")
    audio_object_name = Column(String(500), default="", comment="MinIO中音频对象名")
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
    file_object_name = Column(String(500), nullable=False, comment="PDF在MinIO中的对象名")
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
    chroma_id = Column(String(100), default="", comment="Chroma向量ID")
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
