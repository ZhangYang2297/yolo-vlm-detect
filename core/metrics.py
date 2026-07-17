from prometheus_client import Counter, Histogram, Gauge, Info
from config.settings import get_settings

settings = get_settings()

SYSTEM_INFO = Info("analyzer_system", "系统信息")
SYSTEM_INFO.info({"version": "1.0.0", "environment": settings.flask.env})

# === YOLO 检测指标 ===
YOLO_INFERENCE_TOTAL = Counter(
    "yolo_inference_total", "YOLO推理总次数", ["device", "model"]
)
YOLO_INFERENCE_DURATION = Histogram(
    "yolo_inference_duration_seconds", "YOLO推理耗时(秒)",
    ["device", "mode"], buckets=[0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
)
YOLO_DETECTED_OBJECTS = Counter(
    "yolo_detected_objects_total", "检测到的目标数量", ["class_name"]
)

# === VLM 推理指标 ===
VLM_REQUEST_TOTAL = Counter(
    "vlm_request_total", "VLM请求总数", ["model", "status"]
)
VLM_REQUEST_DURATION = Histogram(
    "vlm_request_duration_seconds", "VLM请求耗时(秒)",
    ["model"], buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)
VLM_CACHE_HITS = Counter("vlm_cache_hits_total", "VLM缓存命中次数")
VLM_CACHE_MISSES = Counter("vlm_cache_misses_total", "VLM缓存未命中次数")
VLM_TOKENS_USED = Counter("vlm_tokens_used_total", "VLM Token消耗", ["type"])

# === 音频分析指标 ===
AUDIO_ANALYSIS_TOTAL = Counter(
    "audio_analysis_total", "音频分析总次数", ["type"]
)
AUDIO_ABNORMAL_DETECTED = Counter(
    "audio_abnormal_detected_total", "异常音频检测次数", ["sound_type"]
)

# === 队列指标 ===
QUEUE_PUT_TOTAL = Counter("queue_put_total", "入队总数", ["queue_name"])
QUEUE_GET_TOTAL = Counter("queue_get_total", "出队总数", ["queue_name"])
QUEUE_SIZE = Gauge("queue_size", "队列当前积压数量", ["queue_name"])

# === 告警指标 ===
ALARM_TRIGGERED_TOTAL = Counter(
    "alarm_triggered_total", "告警触发总数", ["alarm_type", "severity"]
)
ALARM_SAVE_DURATION = Histogram(
    "alarm_save_duration_seconds", "告警保存耗时(秒)",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)

# === 进程指标 ===
PROCESSES_RUNNING = Gauge(
    "processes_running", "运行中的进程数", ["process_type"]
)
FRAME_DROP_TOTAL = Counter(
    "frame_drop_total", "丢帧总数", ["source_id"]
)
STREAM_RECONNECT_TOTAL = Counter(
    "stream_reconnect_total", "流重连次数", ["source_id"]
)

# === 系统性能指标 ===
SYS_CPU_PERCENT = Gauge("sys_cpu_percent", "CPU利用率(%)")
SYS_MEMORY_PERCENT = Gauge("sys_memory_percent", "内存利用率(%)")
SYS_GPU_UTIL = Gauge("sys_gpu_util_percent", "GPU利用率(%)")
SYS_GPU_MEMORY_MB = Gauge("sys_gpu_memory_used_mb", "GPU显存占用(MB)")
SYS_GPU_TEMP = Gauge("sys_gpu_temp_celsius", "GPU温度(°C)")
