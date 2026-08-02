# 新会话交接文档

> 给接手的 AI 助手：读完本文件 + `task_plan.md` 即可掌握项目全貌并继续工作。

## 项目一句话

AI 视频智能分析系统：本地视频 → FFmpeg 推 RTSP → MediaMTX 转 HLS → YOLOv8n(CPU) 检测 → IoU Tracker 跟踪 → ROI 候选事件 → （阶段三接入 VLM 理解 + RAG + Agent）。面向秋招 AI 大模型方向作品集。

## 工作目录

`C:\Users\admin\Documents\yolo-vlm-detct`

## 当前进度

**已完成**：阶段一（基础设施）+ 阶段二（视频分析全链路）+ 前端持久化与体验优化 + MinIO 视频存储。代码已推送 GitHub。

**下一步**：阶段三 VLM 接入。先写实施计划 `docs/superpowers/plans/2026-08-02-VLM候选事件消费实施计划.md`，经用户确认后再写代码。

## 用户偏好（务必遵守）

- 中文回复 + 中文文档；代码/路径/命令保留英文
- 小白视角：每完成一个大模块就更新 `docs/模块开发详解.md`；每步涉及的知识更新 `docs/项目知识手册.md`
- 轻量优先：Redis 队列、MySQL、MinIO、MediaMTX、CPU 推理 YOLOv8n；不引入 Milvus/Kafka/K8s；向量库用 FAISS/Chroma
- 硬件 RTX 4050（当前 GPU 有问题，暂用 CPU，half=False）
- 前端暗色科技风（accent #00d4aa），不引重框架，原生 JS + Bootstrap，预留可扩展侧栏
- 测试用 Playwright 做 UI 自动化；pytest 做后端单测
- 不擅自提交 git，除非用户明确要求

## 启动环境

```powershell
# 1. 启动四个容器（Docker Desktop 必须先运行）
docker start vlm-mysql vlm-redis vlm-minio vlm-mediamtx

# 2. 启动后端（端口 8080，不是 5000）
$env:PYTHONPATH=(Get-Location).Path
python app.py

# 3. 浏览器访问
http://127.0.0.1:8080/monitor      # 实时监测（上传/检测/预览）
http://127.0.0.1:8080/history      # 历史记录
```

容器端口：Redis 6379 / MySQL 3307(root/root123456, db=video_analyzer) / MinIO 9000-9001(minioadmin/minioadmin123) / MediaMTX 8554(RTSP) 8888(HLS)。

## 运行测试

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -m pytest --ignore=tests/e2e -q          # 231 passed
python -m pytest tests/e2e/test_monitor_ui.py -v # Playwright UI（需 Flask 运行中）
```

注意：`tests/` 目录被 `.gitignore` 排除（本地私有，不上传 GitHub），但本地存在。

## 全链路数据流

```
本地 mp4
  → FFmpeg -re 推 RTSP tcp → rtsp://127.0.0.1:8554/pedestrian
  → MediaMTX 转 HLS → http://127.0.0.1:8888/pedestrian/index.m3u8
  → Capture Worker 拉 HLS，解码帧放入有界 FrameBuffer（满则丢旧帧=背压）
  → Inference Worker 取最新帧，YOLOv8n 检测 person
  → IoU Tracker 关联轨迹（tentative→confirmed）
  → Candidate Producer 按 ROI + 冷却去重产出 CandidateEvent
  → MJPEG /detection-preview 实时展示检测框
  → （阶段三）CandidateEvent → Redis 队列 → VLM 理解 → AlarmRecord
```

上传的视频双写：本地 `data/videos/uploads/{uuid}_{name}` + MinIO `videos/` bucket，DB 存 `storage_uri`。

## 关键文件

见 `task_plan.md` 的"关键文件速查"表。核心：
- `app.py` Flask 入口（端口 8080）
- `web/routes/monitor.py` 上传 + start/stop-pipeline（含 HLS 就绪轮询、MinIO 恢复）
- `core/runtime_manager.py` Worker 生命周期
- `workers/` 四个 Worker
- `core/models.py` VideoSource/AnalysisTask/TaskRun/AlarmRecord
- `web/templates/monitor/` 前端页面（index 主页面 / history 历史页 / base 基础模板）
- `web/static/js/i18n.js` 中英双语

## 已知遗留

- 背压丢帧较多（VLM 队列削峰后再调优）
- /alerts-center、/settings 是占位 stub
- MinIO 分片上传/断点续传/加密待开发
- MJPEG 运行时 tab 转圈是 multipart 长连接固有行为（后续可改 WebSocket+Canvas）
- GPU 基准待显卡恢复

## 文档地图

- `task_plan.md` — 任务计划、当前状态、下一步、命令、API（**先读这个**）
- `progress.md` — 按日期的进度日志
- `findings.md` — 踩坑记录与根因
- `docs/模块开发详解.md` — 31 章，每个模块作用/实现/选型/面试话术
- `docs/项目知识手册.md` — 31 章，涉及的所有知识点
- `docs/测试报告/` — UI 修复与排障报告
- `docs/AI视频数据分析系统说明文档.md` — 原始参考项目文档
- `docs/superpowers/plans/` 和 `specs/` — 各阶段设计文档

## Git

远程：https://github.com/ZhangYang2297/yolo-vlm-detect（分支 master）
`.gitignore` 排除：tests/、logs/、data/、*.pt、.env、task_plan.md、findings.md、progress.md、截图产物。
这些 planning 文件是本地私有的，不上传 GitHub，但新会话在同机可读。

## 开始阶段三前要做的

1. 读 `task_plan.md` 的"下一步"部分
2. 用 superpowers-writing-plans skill 写 VLM 实施计划，包含：Redis key 规范、VLM 客户端抽象、prompt 模板、结构化 JSON schema、失败重试/超时/降级、AlarmRecord 落库、RAG 接入点、验收标准
3. 给用户确认后再实现