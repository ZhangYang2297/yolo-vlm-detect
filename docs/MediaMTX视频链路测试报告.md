# MediaMTX 视频链路测试报告

> 测试日期：2026-07-18  
> 测试范围：本地 MP4 → FFmpeg → MediaMTX → RTSP/OpenCV/HLS/WebRTC 入口  
> 结论等级：本机基础功能验证，不等同于生产验收

## 1. 测试目标

本轮先把真实视频送入流媒体服务，为下一步 YOLO 拉流检测建立可重复输入。重点验证：

1. 不修改原始 5 分钟视频，生成 1 分钟以内的测试片段。
2. FFmpeg 能向 MediaMTX 发布 RTSP 流。
3. `ffprobe`、FFmpeg 和 OpenCV 能从 RTSP 获取真实视频。
4. MediaMTX 能生成可访问的 HLS 播放列表和 WebRTC 页面入口。
5. 循环推流能跨越视频结尾，测试结束后不遗留 FFmpeg 进程。

本轮不运行 YOLO/VLM，不测试检测准确率、GPU 性能和音频链路。

## 2. 测试环境

| 项目 | 实际值 |
|---|---|
| 操作系统 | Windows，本机 Docker Desktop |
| FFmpeg | 8.1.1 |
| MediaMTX | v1.19.2，Docker 容器 `vlm-mediamtx` |
| 输入视频 | `data/videos/test.mp4` |
| 测试片段 | `data/videos/test_45s.mp4` |
| RTSP | `rtsp://127.0.0.1:8554/pedestrian` |
| HLS | `http://127.0.0.1:8888/pedestrian/index.m3u8` |
| WebRTC 页面 | `http://127.0.0.1:8889/pedestrian` |

原视频为 H.264、1920×1080、25 FPS、约 300.04 秒，仅包含视频流，没有音轨。

## 3. 测试数据准备

### 3.1 裁剪命令

使用 stream copy 截取前 45 秒，不重新编码，因此处理快且不占用 GPU：

```powershell
ffmpeg -y -ss 0 -i data/videos/test.mp4 -t 45 -c copy data/videos/test_45s.mp4
```

原始 `test.mp4` 保留不变。`ffprobe` 检查结果：

| 指标 | 结果 |
|---|---|
| 时长 | 45.08 秒 |
| 编码 | H.264 |
| 分辨率 | 1920×1080 |
| 帧率 | 25 FPS |
| 大小 | 15,038,213 bytes |
| 音轨 | 无 |

全片解码检查命令：

```powershell
ffmpeg -v error -i data/videos/test_45s.mp4 -f null -
```

结果为 `DECODE_OK`，说明测试片段可以完整解码。

## 4. MediaMTX 配置

当前只允许向 `pedestrian` 路径发布，配置如下：

```yaml
logLevel: info

paths:
  pedestrian:
    source: publisher
```

显式路径白名单比开发期开放任意路径更容易控制，但当前仍未配置发布者/读取者鉴权，不能直接暴露公网。

## 5. 缺陷发现与修复

### D-M01 RTSP 发布返回 400

- **现象**：FFmpeg 首次向 `/pedestrian` 发布时收到 `400 Bad Request`。
- **排查**：查看 MediaMTX 容器日志，发现 `path 'pedestrian' is not configured`。
- **根因**：当前 MediaMTX 配置没有声明可发布的 `pedestrian` 路径，不是视频编码或网络端口问题。
- **修复**：在 `mediamtx.yml` 中增加 `paths.pedestrian.source: publisher`，只重启 MediaMTX。
- **复测**：MediaMTX 接受发布并识别到 1 路 H.264 视频轨道；RTSP、OpenCV 和 HLS 后续测试通过。
- **经验**：客户端的 400 只能说明请求被拒绝，必须结合服务端日志定位；不要盲目重装 FFmpeg 或更换编码器。

## 6. 功能测试结果

| 编号 | 场景 | 验证方法 | 结果 |
|---|---|---|---|
| M-01 | 测试片段可解码 | FFmpeg 全片解码 | 通过 |
| M-02 | RTSP 发布 | FFmpeg 循环发布，MediaMTX 日志识别 H.264 | 通过 |
| M-03 | RTSP 元信息 | `ffprobe` 拉取流信息 | 1920×1080、25 FPS、H.264 |
| M-04 | RTSP 连续解码 | FFmpeg 拉流解码 5 秒 | 通过，`RTSP_DECODE_OK` |
| M-05 | OpenCV 读取 | `VideoCapture` 连续读取 30 帧 | 通过，帧形状 `(1080, 1920, 3)` |
| M-06 | HLS 入口 | HTTP 请求播放列表 | 200，`application/vnd.apple.mpegurl` |
| M-07 | HLS 媒体解码 | FFmpeg 从 HLS 解码 5 秒 | 通过，`HLS_DECODE_OK` |
| M-08 | WebRTC 页面入口 | HTTP 请求页面 | 200，`text/html`，3107 bytes |
| M-09 | 循环边界 | 推流运行超过 45 秒片段结尾 | 通过，累计约 3 分 26 秒 |
| M-10 | 进程清理 | 按 PID/命令行停止后检查 | 通过，无遗留发布进程 |

OpenCV 读取 30 帧耗时约 3.219 秒。该结果只证明能获得有效帧，不是吞吐性能结论，因为客户端加入时间、缓冲和实时节奏都会影响耗时。

### WebRTC 结论边界

本轮只验证 WebRTC HTTP 页面可以访问，**没有验证浏览器 ICE 协商成功，也没有证明浏览器实际播放了媒体**。需要后续用真实浏览器检查视频画面、ICE candidate、UDP 8189、防火墙、断流恢复和公网 NAT 场景。

## 7. 日志告警与技术解释

### 7.1 RTP 包过大

MediaMTX 日志出现：

```text
RTP packets are too big (1460 > 1440), remuxing them into smaller ones
```

MediaMTX 已自动把过大的 RTP 包重新封装为更小的包，本轮没有导致失败。生产环境仍应观察丢包、MTU 和网络路径差异。

### 7.2 客户端中途加入 GOP

拉流时出现过 `co located POCs unavailable`、`mmco: unref short failure` 和 `Missing reference picture`。本轮使用 `-c copy` 保留原视频 GOP；客户端若从 GOP 中间加入，在下一个关键帧到来前可能缺少参考帧，因此出现告警或首屏等待。

生产演示建议重编码并固定 GOP，例如 25 FPS 下每 2 秒一个关键帧：

```powershell
ffmpeg -re -stream_loop -1 -i data/videos/test_45s.mp4 `
  -an -c:v h264_nvenc -preset p4 -b:v 4M `
  -g 50 -keyint_min 50 -sc_threshold 0 `
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/pedestrian
```

如果设备不支持 NVENC，可把 `h264_nvenc` 改为 `libx264`。固定 GOP 会增加少量编码开销，但能改善中途加入、HLS 切片和首帧稳定性。

### 7.3 HLS part 时长变化

日志提示 `part duration changed from 200ms to 236ms`，并说明可能影响 iOS 客户端。根因同样与源视频时间戳、GOP 和直接复制有关。后续需用固定帧率、固定 GOP 的重编码流，在 Safari/iOS 真机复测。

### 7.4 Docker 下 RTSP 传输协议

交付前复验时，未指定传输方式的 `ffprobe` 和 OpenCV 会话选择了 UDP。当前 Compose 只映射 RTSP 控制端口 `8554/tcp`，没有映射 MediaMTX 动态 RTP/RTCP UDP 端口，因此读取端可能等待媒体包并最终超时。显式使用 TCP 后，`ffprobe` 和 FFmpeg 解码恢复正常：

```powershell
ffprobe -rtsp_transport tcp rtsp://127.0.0.1:8554/pedestrian
ffmpeg -rtsp_transport tcp -i rtsp://127.0.0.1:8554/pedestrian -t 5 -f null -
```

后续 Producer 应把 RTSP/TCP 作为当前 Docker 本机方案的明确配置，而不是依赖客户端默认值。OpenCV 后端还需单独验证传输参数确实传给 FFmpeg；不能只设置环境变量后就假定生效。

## 8. 尚未覆盖的测试

| 类别 | 后续测试 |
|---|---|
| WebRTC | 浏览器真实播放、ICE/UDP、NAT、TLS、断线重连 |
| 可靠性 | 主动断流、MediaMTX 重启、发布者重连、消费者重连 |
| 弱网 | 延迟、抖动、丢包、限带宽下的画面与恢复时间 |
| 稳定性 | 1 小时预检、24 小时长稳、内存/句柄增长 |
| 并发 | 1/4/8 路输入，多客户端读取，CPU/内存/网络容量 |
| 安全 | 发布/读取鉴权、路径权限、TLS、端口暴露策略 |
| 音频 | 有音轨视频、音频编码兼容、音画同步、VAD/异常声音 |
| AI | OpenCV/FFmpeg 拉流接 YOLO，FPS、延迟、显存和丢帧策略 |

## 9. 本轮结论

本地 MP4 经 FFmpeg 发布到 MediaMTX 后，RTSP 元信息、RTSP 解码、OpenCV 取帧、HLS 播放列表及 HLS 解码均已完成基础验证；循环发布和进程清理也已验证。WebRTC 当前只完成页面入口检查。

因此，下一开发步骤可以进入“RTSP → YOLO 行人检测”的最小闭环，但在宣称生产可用前，仍必须补齐浏览器 WebRTC、断流重连、弱网、长稳、并发、鉴权和音频测试。
