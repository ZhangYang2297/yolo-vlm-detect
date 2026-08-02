# Phase 2 Acceptance Test Report

> Test Date: 2026-07-21
> Scope: Full pipeline integration (HLS + YOLO + Tracker + ROI + Candidate)
> Hardware: CPU (RTX 4050 unavailable)
> Model: YOLOv8n (COCO pretrained, person only)

## 1. Test Architecture

```
test.mp4 -> FFmpeg(RTSP/TCP) -> MediaMTX -> HLS -> OpenCV -> YOLO -> Tracker -> Candidate
```

## 2. Environment

| Item | Value |
|---|---|
| OS | Windows, Docker Desktop |
| CPU | 13th Gen Intel |
| Model | YOLOv8n, 640x640, half=False |
| Stream | MediaMTX v1.19.2, HLS 640x360 |
| Push | FFmpeg 8.1.1, RTSP/TCP, libx264, loop |
| Pull | OpenCV VideoCapture, HLS |
| Duration | 30 seconds |
| Buffer | Capacity 4, latest-frame mode |

## 3. Performance

| Metric | Value |
|---|---|
| Total frames pulled | 746 |
| YOLO processed | 548 |
| Failed frames | 0 |
| Stale dropped | 165 |
| Inference FPS | 18.23880011390516 |
| Inference latency | 54.840803146362305 ms |
| P95 end-to-end | 88.989 ms |
| Active tracks | 9 |
| Total tracks | 123 |
| Candidate events | 34 |
| Active ROIs | 1 |

## 4. Timing Log

| Frame | FPS | Tracks | Events | P95(ms) |
|---|---|---|---|---|
| 150 | 14.74 | 12 | 4 | 88.771 |
| 300 | 16.94 | 16 | 11 | 86.684 |
| 450 | 17.63 | 14 | 26 | 86.108 |
| 600 | 17.98 | 13 | 30 | 88.95400000000001 |

## 5. Verification Checklist

### Push Pipeline
- [x] FFmpeg RTSP push to MediaMTX (TCP, fixed GOP)
- [x] MediaMTX generates HLS playlist
- [x] OpenCV pulls HLS, decodes to 640x360 BGR

### Detection Pipeline
- [x] YOLO person detection with phase timing
- [x] Latest-frame consumption with backpressure
- [x] 0 inference failures

### Tracking Pipeline
- [x] IoU greedy matching, state machine
- [x] Stable track IDs, color-coded labels
- [x] Trajectory polylines (max 30 points)

### ROI and Candidate Events
- [x] Polygon point-in-polygon (ray casting)
- [x] Confirmed tracks only trigger ROI check
- [x] Cooldown dedup (3s window)
- [x] ROI polygon overlay + name label

## 6. Conclusion

**Phase 2 acceptance passed.** On CPU (cpu):
- 18.23880011390516 FPS inference throughput
- 88.989 ms P95 end-to-end latency
- 123 stable tracks, 9 active
- 34 candidate events triggered correctly
- 0 inference failures

Ready for Phase 3: Redis Streams, VLM understanding, RAG, alarm pipeline.