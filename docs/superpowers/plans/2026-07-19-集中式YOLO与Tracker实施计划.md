# 集中式 YOLO 与 Tracker 实施计划

> 日期：2026-07-19  
> 阶段：总路线图阶段 2  
> 开发方式：按可展示的纵向切片递进，每完成一个核心模块，同步补后端接口、前端页面、自动化测试和学习文档。
> 当前进度：切片 A、B、C 已完成，集中式 YOLO 已通过本地 MP4 CPU 冒烟；切片 B 专项为 `37 passed`，全量为 `181 passed, 13 warnings`，下一步执行切片 D ROI、去重与候选触发。

## 1. 阶段目标

把阶段一的任务配置和运行记录连接到真实视频处理链路：

```text
VideoSource/TaskRun -> Capture Worker -> Inference Worker -> Tracker -> CandidateEvent
                              |                 |              |
                              +------ 运行状态、预览和指标 -----+
```

阶段二只产出检测、轨迹和候选事件，不调用 VLM、不写 Redis Streams、不生成最终告警。这样可以单独测清拉流、推理、跟踪和背压，避免错误跨模块扩散。

## 2. 每个切片必须交付

1. 核心能力：可脱离 Web 单测的 Python 模块。
2. 后端接口：统一响应信封、明确状态码和错误码。
3. 前端页面：能看到当前真实状态，不展示伪造数据。
4. 学习文档：说明作用、原理、代码路径、异常、测试和面试表达。

## 3. 核心数据契约

### 3.1 FramePacket

| 字段 | 类型 | 规则 | 作用 |
|---|---|---|---|
| `task_id` | int | `> 0` | 对应分析任务 |
| `run_id` | int | `> 0` | 对应本次运行 |
| `trace_id` | str | 非空 UUID 字符串 | 串联一帧的处理日志 |
| `frame_index` | int | `>= 0` | 源内帧序号 |
| `source_timestamp_ms` | float | `>= 0` | 视频源时间轴位置 |
| `captured_at` | datetime | UTC 时间 | 系统收到帧的时间 |
| `frame` | ndarray | 非空 `HxWx3 BGR` | OpenCV 图像 |

帧数据只在进程内传递，不编码成 Base64 放 Redis。进入后续 Redis Stream 的只会是事件元数据和对象引用。

### 3.2 TrackResult

包含 `task_id`、`run_id`、`trace_id`、`track_id`、类别、置信度、边界框、轨迹年龄、是否命中 ROI 和轨迹状态。`track_id` 只保证在单次 `run_id` 内唯一。

### 3.3 CandidateEvent

包含 `event_id`、`task_id`、`run_id`、`trace_id`、`track_id`、候选类型、代表帧引用、源时间窗口和触发原因。阶段二先在内存中产出，阶段三再定义 Redis Streams 序列化契约。

## 4. 纵向切片

### 切片 A：Capture Worker 与原始画面【已完成】

- `core/stream_client.py`：封装 OpenCV 拉流，隔离文件、RTSP 和测试替身。
- `workers/contracts.py`：跨模块数据契约。
- `workers/frame_buffer.py`：有界最新帧缓冲和环形历史帧缓冲。
- `workers/capture_worker.py`：拉流、抽帧、时间戳、重连、EOF 和背压。
- `core/runtime_manager.py`：开发环境嵌入式线程生命周期；核心 Worker 不依赖 Flask。
- `GET /api/analysis-tasks/{id}/runtime`：运行状态、帧计数、丢帧和最近错误。
- `GET /api/analysis-tasks/{id}/preview`：调试用 MJPEG 原始画面；无帧返回稳定错误。
- `/live/{task_id}`：显示原始画面和 Capture 指标。

异常规则：源打不开进入 `failed`；短暂读帧失败按上限重连；本地文件 EOF 在演示模式循环；队列满时丢最旧帧；停止必须释放 `VideoCapture`。

验收证据：专项测试覆盖状态、EOF、失败、背压、幂等停止、API、MJPEG 和缓冲释放；本地 `data/videos/test.mp4` 可持续读帧，停止后线程、句柄和缓冲均释放。MJPEG 仍只定位为开发调试预览。

### 切片 B：集中式 Inference Worker 与检测画面【已完成】

- 单例加载一个 YOLO 模型，多任务复用，禁止每路视频重复加载权重。
- 公平轮询各任务的最新帧；只消费最新帧，过期帧直接丢弃。
- 输出 `FrameDetections`，保存预处理、推理、后处理和端到端耗时。
- 页面增加检测人数、推理 FPS 和 P95 延迟。
- CPU 默认使用 `yolov8n.pt`，GPU 恢复后再配置 `cuda/half`。

验收证据：共享检测器、公平轮询、最新帧背压、失败隔离、分阶段耗时、P95、Runtime 生命周期、检测 MJPEG 和布尔配置边界均有自动化测试；真实 `1080p MP4 + yolov8n + CPU` 产出 person 检测和带框帧，配置确认 `half=False`。短时冷启动 P95 较高，已在学习文档中区分冷启动与稳态指标。

### 切片 C：Tracker 与轨迹可视化【已完成】

- 先实现可解释、可单测的 IoU 匹配 Tracker，不立即引入重型 ReID。
- 轨迹经过 `tentative -> confirmed -> lost -> removed` 状态。
- 页面显示 `track_id`、轨迹数量和短轨迹线。
- 遮挡恢复能力不足时再评估 ByteTrack/BoT-SORT。

### 切片 D：ROI、去重与候选触发

- 支持多边形 ROI，边界点视为命中。
- 同一轨迹在冷却窗口内只触发一次，避免 VLM 重复调用。
- 候选只保存代表帧和时间窗口，不在阶段二生成告警结论。
- 页面增加 ROI 覆盖层和候选事件列表。

### 切片 E：阶段验收

- 单元测试覆盖正常、异常、边界、资源释放和并发停止。
- 集成测试使用本地视频和 MediaMTX RTSP 各跑一轮。
- 记录 Capture FPS、Inference FPS、P50/P95/P99、丢帧数和内存。
- 更新 `阶段二测试报告.md`、`模块开发详解.md`、`项目知识手册.md` 和文档导航。

## 5. 运行模式与生产边界

为了让单台笔记本能立即演示，阶段二先提供嵌入 Flask 进程的开发运行器。它只负责线程注册、启动、停止和读取快照，不把业务逻辑写进路由。

生产部署时，Capture/Inference 应作为独立进程运行，Web 通过 Redis 心跳和控制消息读取状态。该进程拆分属于阶段三；阶段二不得把开发运行器描述成最终生产架构。

## 6. 背压与并发规则

- 每个视频源只有一个 Capture 写入者。
- 帧缓冲有固定容量；写满后删除最旧帧并增加 `dropped_frames`。
- Inference 获取最新帧时可清理更旧帧，保证实时性而不是完整逐帧处理。
- 状态快照加锁；耗时解码、推理和 JPEG 编码不长期持锁。
- `start` 幂等；`stop` 可重复调用；停止线程有超时。

## 7. 接口验证规则

- 不存在的任务返回 `404 TASK_NOT_FOUND`。
- 尚未启动返回 `409 RUNTIME_NOT_STARTED`，而不是空白 200。
- MJPEG 只用于本机调试，响应禁止缓存；正式预览仍由 MediaMTX WebRTC/HLS 承担。
- API 不返回带用户名和密码的 RTSP 原始地址。
- 前端对网络错误、运行失败和无帧状态给出可读提示。

## 8. 测试顺序

1. 先写 `FramePacket`、缓冲区和 Capture 状态机失败测试。
2. 实现最小代码，再补重连、EOF、丢旧帧和释放资源测试。
3. 写 runtime API 和页面路由测试，再接开发运行器。
4. 每个切片先跑专项测试，再跑全量回归。
5. 自动化通过后才运行真实视频与 RTSP 冒烟测试。

## 9. 阶段二完成标准

- 本地 MP4 和 MediaMTX RTSP 均可持续拉流。
- 一个 YOLO 实例可公平处理至少两个模拟视频源。
- 检测目标拥有稳定的 `track_id`，队列积压时可量化丢旧帧。
- 页面能观察原始帧、检测框、轨迹、候选事件和性能指标。
- 停止任务后线程、句柄和缓冲均释放。
- 文档只标记真实实现和真实测试过的能力。
