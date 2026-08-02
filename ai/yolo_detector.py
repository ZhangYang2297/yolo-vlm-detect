from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Protocol

import numpy as np


@dataclass(frozen=True)
class RawDetection:
    class_id: int
    confidence: float
    xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class BackendPrediction:
    detections: tuple[RawDetection, ...] = ()
    preprocess_ms: float = 0.0
    inference_ms: float = 0.0
    postprocess_ms: float = 0.0


class DetectionBackend(Protocol):
    def predict(self, frame: np.ndarray, **kwargs: object) -> BackendPrediction: ...


class UltralyticsBackend:
    def __init__(self, model: object) -> None:
        self.model = model

    @classmethod
    def from_model_path(cls, model_path: str) -> "UltralyticsBackend":
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is not installed. Run 'pip install ultralytics'."
            ) from exc
        return cls(model=YOLO(model_path))

    def predict(
        self,
        frame: np.ndarray,
        *,
        classes: tuple[int, ...],
        confidence: float,
        iou_threshold: float,
        image_size: int,
        device: str,
        half: bool,
    ) -> BackendPrediction:
        results = self.model.predict(
            source=frame,
            classes=list(classes),
            conf=confidence,
            iou=iou_threshold,
            imgsz=image_size,
            device=device,
            half=half,
            verbose=False,
        )
        if not results:
            return BackendPrediction()

        result = results[0]
        speed = result.speed or {}
        boxes = result.boxes
        if boxes is None:
            detections: tuple[RawDetection, ...] = ()
        else:
            class_ids = boxes.cls.cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            coordinates = boxes.xyxy.cpu().tolist()
            detections = tuple(
                RawDetection(
                    class_id=int(class_id),
                    confidence=float(confidence_value),
                    xyxy=tuple(float(value) for value in coordinate),
                )
                for class_id, confidence_value, coordinate in zip(
                    class_ids, confidences, coordinates
                )
            )

        return BackendPrediction(
            detections=detections,
            preprocess_ms=float(speed.get("preprocess", 0.0)),
            inference_ms=float(speed.get("inference", 0.0)),
            postprocess_ms=float(speed.get("postprocess", 0.0)),
        )


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]


@dataclass(frozen=True)
class FrameDetections:
    frame_index: int
    timestamp_ms: float
    image_width: int
    image_height: int
    detections: tuple[Detection, ...]
    preprocess_ms: float
    inference_ms: float
    postprocess_ms: float
    model_total_ms: float
    total_ms: float


def _torch_cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


class YoloDetector:
    PERSON_CLASS_ID = 0

    def __init__(
        self,
        backend: DetectionBackend,
        model_name: str = "yolov8s.pt",
        device: str = "cuda",
        half: bool = True,
        confidence: float = 0.5,
        iou_threshold: float = 0.45,
        image_size: int = 640,
        cuda_available: Callable[[], bool] = _torch_cuda_available,
    ) -> None:
        normalized_device = str(device).lower()
        if normalized_device.startswith("cuda") and not cuda_available():
            raise RuntimeError(
                "CUDA was requested but is not available; install a CUDA-enabled "
                "PyTorch build or explicitly use device='cpu'."
            )

        self.backend = backend
        self.model_name = model_name
        self.device = normalized_device
        self.half = bool(half and normalized_device != "cpu")
        self.confidence = float(confidence)
        self.iou_threshold = float(iou_threshold)
        self.image_size = int(image_size)

    def detect(
        self,
        frame: np.ndarray,
        frame_index: int = 0,
        timestamp_ms: float = 0.0,
    ) -> FrameDetections:
        if (
            frame is None
            or not isinstance(frame, np.ndarray)
            or frame.size == 0
            or frame.ndim != 3
            or frame.shape[2] != 3
        ):
            raise ValueError("Expected a non-empty HxWx3 BGR frame.")

        started_at = perf_counter()
        prediction = self.backend.predict(
            frame,
            classes=(self.PERSON_CLASS_ID,),
            confidence=self.confidence,
            iou_threshold=self.iou_threshold,
            image_size=self.image_size,
            device=self.device,
            half=self.half,
        )
        detections = tuple(
            Detection(
                class_id=item.class_id,
                class_name="person",
                confidence=item.confidence,
                xyxy=item.xyxy,
            )
            for item in prediction.detections
            if item.class_id == self.PERSON_CLASS_ID
        )
        model_total_ms = (
            prediction.preprocess_ms
            + prediction.inference_ms
            + prediction.postprocess_ms
        )
        elapsed_ms = (perf_counter() - started_at) * 1000.0

        return FrameDetections(
            frame_index=int(frame_index),
            timestamp_ms=float(timestamp_ms),
            image_width=int(frame.shape[1]),
            image_height=int(frame.shape[0]),
            detections=detections,
            preprocess_ms=float(prediction.preprocess_ms),
            inference_ms=float(prediction.inference_ms),
            postprocess_ms=float(prediction.postprocess_ms),
            model_total_ms=float(model_total_ms),
            total_ms=max(elapsed_ms, model_total_ms),
        )
