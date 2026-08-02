from __future__ import annotations

import argparse
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

import cv2
import psutil

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.benchmark import BenchmarkCollector, write_json_report
from ai.yolo_detector import FrameDetections, UltralyticsBackend, YoloDetector


@dataclass(frozen=True)
class BenchmarkOptions:
    source: Path
    output_dir: Path
    model: str = "model_weights/yolov8s.pt"
    device: str = "cuda"
    half: bool = True
    confidence: float = 0.5
    iou_threshold: float = 0.45
    image_size: int = 640
    frame_stride: int = 1
    max_frames: int | None = None
    warmup_frames: int = 10
    sample_every: int = 100
    save_video: bool = False


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark YOLO person detection.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="model_weights/yolov8s.pt")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--iou-threshold", type=float, default=0.45)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--warmup-frames", type=int, default=10)
    parser.add_argument("--sample-every", type=int, default=100)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--half", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _validate_options(options: BenchmarkOptions) -> None:
    if not options.source.is_file():
        raise FileNotFoundError(f"Video source does not exist: {options.source}")
    if options.frame_stride < 1:
        raise ValueError("frame_stride must be at least 1.")
    if options.max_frames is not None and options.max_frames < 1:
        raise ValueError("max_frames must be at least 1.")
    if options.warmup_frames < 0:
        raise ValueError("warmup_frames cannot be negative.")
    if options.sample_every < 1:
        raise ValueError("sample_every must be at least 1.")


def _default_detector_factory(options: BenchmarkOptions) -> YoloDetector:
    backend = UltralyticsBackend.from_model_path(options.model)
    return YoloDetector(
        backend=backend,
        model_name=options.model,
        device=options.device,
        half=options.half,
        confidence=options.confidence,
        iou_threshold=options.iou_threshold,
        image_size=options.image_size,
    )


def _draw_detections(frame, result: FrameDetections):
    annotated = frame.copy()
    for detection in result.detections:
        left, top, right, bottom = (int(value) for value in detection.xyxy)
        cv2.rectangle(annotated, (left, top), (right, bottom), (0, 220, 0), 2)
        label = f"person {detection.confidence:.2f}"
        cv2.putText(
            annotated,
            label,
            (left, max(20, top - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 220, 0),
            2,
            cv2.LINE_AA,
        )
    return annotated


def _gpu_memory_mb(device: str) -> float | None:
    if not device.startswith("cuda"):
        return None
    import torch

    return torch.cuda.max_memory_allocated() / (1024 * 1024)


def _software_metadata() -> dict[str, str | bool | None]:
    try:
        import torch

        torch_version = torch.__version__
        cuda_version = torch.version.cuda
        gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except ImportError:
        torch_version = None
        cuda_version = None
        gpu_name = None
    try:
        import ultralytics

        ultralytics_version = ultralytics.__version__
    except ImportError:
        ultralytics_version = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "opencv": cv2.__version__,
        "torch": torch_version,
        "cuda_runtime": cuda_version,
        "gpu_name": gpu_name,
        "ultralytics": ultralytics_version,
    }


def benchmark_video(
    options: BenchmarkOptions,
    detector_factory: Callable[[BenchmarkOptions], YoloDetector] = _default_detector_factory,
) -> dict:
    _validate_options(options)
    options.output_dir.mkdir(parents=True, exist_ok=True)

    load_started = perf_counter()
    detector = detector_factory(options)
    model_load_ms = (perf_counter() - load_started) * 1000.0

    capture = cv2.VideoCapture(str(options.source))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {options.source}")

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    ok, first_frame = capture.read()
    if not ok or first_frame is None:
        capture.release()
        raise RuntimeError(f"Video has no decodable frames: {options.source}")

    cold_started = perf_counter()
    detector.detect(first_frame, frame_index=0, timestamp_ms=0.0)
    cold_start_ms = (perf_counter() - cold_started) * 1000.0
    for warmup_index in range(options.warmup_frames):
        ok, warmup_frame = capture.read()
        if not ok:
            break
        detector.detect(warmup_frame, frame_index=warmup_index + 1)

    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    if options.device.startswith("cuda"):
        import torch

        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()

    collector = BenchmarkCollector()
    process = psutil.Process()
    frame_records = []
    processed_frames = 0
    source_frame_index = -1
    video_writer = None
    if options.save_video:
        output_fps = source_fps / options.frame_stride if source_fps > 0 else 25.0
        video_writer = cv2.VideoWriter(
            str(options.output_dir / "annotated.mp4"),
            cv2.VideoWriter_fourcc(*"mp4v"),
            output_fps,
            (source_width, source_height),
        )
        if not video_writer.isOpened():
            capture.release()
            raise RuntimeError("Could not create annotated video writer.")

    benchmark_started = perf_counter()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            source_frame_index += 1
            if source_frame_index % options.frame_stride != 0:
                continue
            if options.max_frames is not None and processed_frames >= options.max_frames:
                break

            timestamp_ms = (
                source_frame_index * 1000.0 / source_fps if source_fps > 0 else 0.0
            )
            result = detector.detect(
                frame,
                frame_index=source_frame_index,
                timestamp_ms=timestamp_ms,
            )
            process_memory_mb = process.memory_info().rss / (1024 * 1024)
            collector.add(
                result,
                memory_mb=process_memory_mb,
                gpu_memory_mb=_gpu_memory_mb(options.device),
            )
            frame_records.append(asdict(result))

            needs_annotation = (
                processed_frames % options.sample_every == 0 or video_writer is not None
            )
            if needs_annotation:
                annotated = _draw_detections(frame, result)
                if processed_frames % options.sample_every == 0:
                    cv2.imwrite(
                        str(
                            options.output_dir
                            / f"sample_{source_frame_index:06d}.jpg"
                        ),
                        annotated,
                    )
                if video_writer is not None:
                    video_writer.write(annotated)
            processed_frames += 1
    finally:
        capture.release()
        if video_writer is not None:
            video_writer.release()

    if options.device.startswith("cuda"):
        import torch

        torch.cuda.synchronize()
    elapsed_seconds = perf_counter() - benchmark_started
    metadata = {
        "model": options.model,
        "device": detector.device,
        "half": detector.half,
        "image_size": options.image_size,
        "confidence": options.confidence,
        "iou_threshold": options.iou_threshold,
        "frame_stride": options.frame_stride,
        "warmup_frames": options.warmup_frames,
        "model_load_ms": model_load_ms,
        "cold_start_ms": cold_start_ms,
        "source": {
            "path": str(options.source.resolve()),
            "fps": source_fps,
            "width": source_width,
            "height": source_height,
            "frame_count": source_frame_count,
        },
        "software": _software_metadata(),
    }
    summary = collector.summary(elapsed_seconds=elapsed_seconds, metadata=metadata)
    write_json_report(options.output_dir / "benchmark.json", summary)
    write_json_report(options.output_dir / "frames.json", {"frames": frame_records})
    return summary


def main() -> int:
    args = create_parser().parse_args()
    options = BenchmarkOptions(
        source=args.source,
        output_dir=args.output_dir,
        model=args.model,
        device=args.device,
        half=args.half,
        confidence=args.confidence,
        iou_threshold=args.iou_threshold,
        image_size=args.image_size,
        frame_stride=args.frame_stride,
        max_frames=args.max_frames,
        warmup_frames=args.warmup_frames,
        sample_every=args.sample_every,
        save_video=args.save_video,
    )
    summary = benchmark_video(options)
    print(f"Processed {summary['processed_frames']} frames")
    print(f"Actual FPS: {summary['actual_fps']:.2f}")
    print(f"P95 total latency: {summary['latency_ms']['total']['p95']:.2f} ms")
    print(f"Report: {(options.output_dir / 'benchmark.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
