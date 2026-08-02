# 前端 UI 中文化与上传流程修复测试报告

- 报告日期：2026-07-21
- 测试范围：`/monitor` 页面中文化、语言切换、上传进度、启动管线全流程
- 测试工具：Playwright 1.61 + Chromium（无头）
- 服务端：Flask 开发服务器 `http://127.0.0.1:8080`
- 测试脚本：`tests/e2e/test_monitor_ui.py`

## 一、修复背景

上一版本 UI 存在两大问题：

1. **全英文界面**——用户要求提供中文界面或语言切换。
2. **上传后一直转圈圈**——`fetch()` 无法回报大文件上传进度，104 MB 测试视频在慢速本地写盘时看不到反馈；同时后端 `video_sources.name` 唯一约束导致同名文件二次上传直接 500。

## 二、修复要点

| 模块 | 变更 |
|---|---|
| `web/static/js/i18n.js` | 新增前端 i18n 字典（zh/en），提供 `window.I18N.setLang / toggle`，通过 `data-i18n` / `data-i18n-attr` 声明式绑定，切换后写 `localStorage` 持久化 |
| `web/templates/monitor/base.html` | 顶栏右侧新增语言切换按钮；状态点四态（idle/warn/live/error）；引入 i18n.js |
| `web/templates/monitor/index.html` | 统一模板、去掉多层 `<script>` 嵌套错误；上传改为 `XMLHttpRequest` + 真实进度条；三步流程指示器（上传→启动→检测）；预览失败重试面板；自动开始复选框 |
| `web/routes/monitor.py` | `VideoSource.name` 追加短 UUID 后缀，避免同名唯一约束冲突 |

## 三、测试用例与结果

| 编号 | 用例 | 期望 | 结果 |
|---|---|---|---|
| TC-01 | 默认语言 | `<html lang="zh-CN">`，上传按钮显示"上传视频"，侧栏 Tab 中文 | ✅ 通过 |
| TC-02 | 中英互切 | 点击右上角切换按钮：`html.lang` 切至 `en`，按钮切到 `Upload Video`；再点回中文 | ✅ 通过 |
| TC-03 | 语言持久化 | 切换到英文后刷新页面，UI 仍为英文（`localStorage.vlm.lang`） | ✅ 通过 |
| TC-04 | 流程指示器 | 未上传时 `flowStep1` 处于 `doing` 状态 | ✅ 通过 |
| TC-05 | 上传进度 | 选择 104 MB 视频后：进度条可见、状态文案变为"已上传：test.mp4"、开始按钮启用、任务信息面板显示 `#taskId` 与文件名 | ✅ 通过 |
| TC-06 | 启动管线 | 上传后点"开始分析"：20 s 内进入 running 或 failed；running 时 `#detectionPreview` 或 `#previewError` 至少一个可见；点"停止"后状态变"已停止" | ✅ 通过 |

**汇总**：6 passed, 0 failed（运行时长约 16 秒）。

### 截图证据

- `docs/测试报告/playwright_artifacts/01_default_zh.png` 默认中文视图
- `docs/测试报告/playwright_artifacts/02_switched_en.png` 切换到英文
- `docs/测试报告/playwright_artifacts/03_uploading.png` 上传进度条状态
- `docs/测试报告/playwright_artifacts/04_uploaded_ready.png` 上传完成、任务信息面板已填充
- `docs/测试报告/playwright_artifacts/05_pipeline_*.png` 点击"开始分析"后的状态

## 四、复现步骤

```powershell
# 1. 启动依赖容器 + 后端
scripts/start.ps1

# 2. 安装 Playwright（首次）
pip install playwright
python -m playwright install chromium

# 3. 运行 UI 测试
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/e2e/test_monitor_ui.py -v
```

## 五、遗留问题与后续工作

1. **管线启动经常落入 failed 分支**：`start-pipeline` 内固定 `time.sleep(2)` 等 FFmpeg 推流稳定，但 MediaMTX HLS 实际就绪时间抖动较大；建议后续用轮询 `http://127.0.0.1:8888/pedestrian/index.m3u8` 状态代替死等。
2. **MJPEG 预览容错**：目前依赖前端 `<img>` `onerror` 三次重试；当 Runtime 未就绪返回 409 时，前端能给出"检测画面暂不可用，请稍后重试"面板，但可以在后端返回带原因的 JSON 错误让 UI 显示更精细的提示。
3. **上传进度阶段化**：目前进度条只覆盖上传阶段，服务器落盘和入库耗时未反馈；下一步可在响应中附带 `saved_at`, `probe_ms` 等指标进一步细化。
4. **告警/历史/设置** 三个导航项当前只是占位（`href="#"`），阶段三需要补齐。
