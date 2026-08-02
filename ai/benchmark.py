from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

from ai.yolo_detector import FrameDetections


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def _latency_stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": fmean(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "min": min(values),
        "max": max(values),
    }


class BenchmarkCollector:
    def __init__(self) -> None:
        self._frames: list[FrameDetections] = []
        self._memory_mb: list[float] = []
        self._gpu_memory_mb: list[float] = []

    def add(
        self,
        frame: FrameDetections,
        memory_mb: float | None = None,
        gpu_memory_mb: float | None = None,
    ) -> None:
        self._frames.append(frame)
        if memory_mb is not None:
            self._memory_mb.append(float(memory_mb))
        if gpu_memory_mb is not None:
            self._gpu_memory_mb.append(float(gpu_memory_mb))

    def summary(
        self,
        elapsed_seconds: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._frames:
            raise ValueError("No benchmark frames were collected.")
        if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
            raise ValueError("elapsed_seconds must be a positive finite number.")

        latency_series = {
            "preprocess": [frame.preprocess_ms for frame in self._frames],
            "inference": [frame.inference_ms for frame in self._frames],
            "postprocess": [frame.postprocess_ms for frame in self._frames],
            "model_total": [frame.model_total_ms for frame in self._frames],
            "total": [frame.total_ms for frame in self._frames],
        }
        result: dict[str, Any] = dict(metadata or {})
        result.update(
            {
                "processed_frames": len(self._frames),
                "total_detections": sum(
                    len(frame.detections) for frame in self._frames
                ),
                "elapsed_seconds": float(elapsed_seconds),
                "actual_fps": len(self._frames) / elapsed_seconds,
                "latency_ms": {
                    name: _latency_stats(values)
                    for name, values in latency_series.items()
                },
                "resources": {
                    "process_memory_peak_mb": max(self._memory_mb, default=None),
                    "gpu_memory_peak_mb": max(self._gpu_memory_mb, default=None),
                },
            }
        )
        return result


def write_json_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    output_path.write_text(content + "\n", encoding="utf-8")
    return output_path
