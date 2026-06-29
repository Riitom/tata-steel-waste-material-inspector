from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import torch
import yaml
from PIL import Image, ImageDraw, ImageFont

from .settings import Settings


class YoloInferenceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = settings.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.class_names = self._load_class_names(settings.dataset_config_path)
        self.load_error: str | None = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if not self.settings.model_path.exists():
            raise FileNotFoundError(f"YOLO checkpoint not found: {self.settings.model_path}")

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is required for YOLO inference. Install ultralytics first.") from exc

        model = YOLO(str(self.settings.model_path))
        model_names = getattr(model, "names", None)
        if model_names:
            self.class_names = self._normalize_names(model_names)
        self.model = model
        self.load_error = None

    def predict(
        self,
        image: Image.Image,
        confidence: float,
        max_detections: int,
    ) -> tuple[list[dict[str, Any]], Image.Image]:
        if self.model is None:
            raise RuntimeError(self.load_error or "The YOLO model is not loaded.")

        rgb_image = image.convert("RGB")
        with self._lock:
            results = self.model.predict(
                source=rgb_image,
                conf=confidence,
                max_det=max_detections,
                imgsz=self.settings.model_imgsz,
                device=self.device,
                verbose=False,
            )

        detections = self._detections_from_result(results[0] if results else None, max_detections)
        return detections, self.draw_predictions(rgb_image, detections)

    def _detections_from_result(self, result: Any, max_detections: int) -> list[dict[str, Any]]:
        if result is None or getattr(result, "boxes", None) is None:
            return []

        detections = []
        mask_polygons = self._mask_polygons_from_result(result)
        for index, box in enumerate(result.boxes):
            class_id = int(box.cls[0].item())
            score = float(box.conf[0].item())
            xyxy = [round(float(value), 2) for value in box.xyxy[0].detach().cpu().tolist()]
            mask_polygon = mask_polygons[index] if index < len(mask_polygons) else None
            mask_area_px = self._polygon_area(mask_polygon) if mask_polygon else None
            detections.append(
                {
                    "label": self.class_names.get(class_id, f"class_{class_id}"),
                    "class_id": class_id,
                    "confidence": round(score, 6),
                    "box_xyxy": xyxy,
                    "mask_area_px": round(mask_area_px, 4) if mask_area_px else None,
                    "area_method": "segmentation_mask_area" if mask_area_px else None,
                    "mask_polygon": mask_polygon,
                }
            )
            if len(detections) >= max_detections:
                break
        return detections

    @classmethod
    def _load_class_names(cls, config_path: Path) -> dict[int, str]:
        if not config_path.exists():
            return {}
        if config_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return cls._normalize_names(data.get("names", {}))

        data = json.loads(config_path.read_text(encoding="utf-8"))
        categories = sorted(data.get("categories", []), key=lambda item: int(item["id"]))
        return {index: str(category["name"]) for index, category in enumerate(categories)}

    @staticmethod
    def _normalize_names(names: Any) -> dict[int, str]:
        if isinstance(names, list):
            return {index: str(name) for index, name in enumerate(names)}
        if isinstance(names, dict):
            return {int(index): str(name) for index, name in names.items()}
        return {}

    def draw_predictions(
        self,
        image: Image.Image,
        detections: list[dict[str, Any]],
    ) -> Image.Image:
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        font_size = max(14, min(28, round(min(image.size) * 0.025)))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        line_width = max(3, round(min(image.size) * 0.004))

        for detection in detections:
            x1, y1, x2, y2 = detection["box_xyxy"]
            label = f"{detection['label'].replace('_', ' ')} {detection['confidence']:.2f}"
            weight_min = detection.get("expected_weight_min_kg")
            weight_max = detection.get("expected_weight_max_kg")
            if weight_min is not None and weight_max is not None:
                label += f" {weight_min:.2f}-{weight_max:.2f}kg"
            color = self._color_for_label(detection["label"])
            mask_polygon = detection.get("mask_polygon")
            if mask_polygon and len(mask_polygon) >= 3:
                polygon_points = [(float(x), float(y)) for x, y in mask_polygon]
                draw.line(
                    polygon_points + [polygon_points[0]],
                    fill=color,
                    width=max(2, line_width - 1),
                )
            draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)
            text_bbox = draw.textbbox((x1, y1), label, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            label_y = max(0, y1 - text_height - 10)
            draw.rectangle(
                (x1, label_y, x1 + text_width + 12, label_y + text_height + 10),
                fill=color,
            )
            draw.text((x1 + 6, label_y + 5), label, fill=(255, 255, 255), font=font)
        return annotated

    @staticmethod
    def _color_for_label(label: str) -> tuple[int, int, int]:
        seed = sum(ord(char) for char in label)
        return (
            35 + (seed * 53) % 190,
            45 + (seed * 97) % 180,
            45 + (seed * 193) % 180,
        )

    @staticmethod
    def _mask_polygons_from_result(result: Any) -> list[list[list[float]] | None]:
        masks = getattr(result, "masks", None)
        polygons = getattr(masks, "xy", None) if masks is not None else None
        if polygons is None:
            return []

        normalized: list[list[list[float]] | None] = []
        for polygon in polygons:
            points = polygon.tolist() if hasattr(polygon, "tolist") else polygon
            clean_points = []
            for point in points:
                if len(point) >= 2:
                    clean_points.append([round(float(point[0]), 2), round(float(point[1]), 2)])
            normalized.append(clean_points if len(clean_points) >= 3 else None)
        return normalized

    @staticmethod
    def _polygon_area(polygon: list[list[float]] | None) -> float | None:
        if not polygon or len(polygon) < 3:
            return None
        area = 0.0
        for index, point in enumerate(polygon):
            next_point = polygon[(index + 1) % len(polygon)]
            area += point[0] * next_point[1] - next_point[0] * point[1]
        return abs(area) * 0.5
