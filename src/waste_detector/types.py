from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MaterialProfile:
    name: str
    category: str
    density_kg_m3: float
    default_thickness_cm: float
    box_fill_ratio: float = 0.6
    calibration_factor: float = 1.0
    weight_uncertainty_ratio: float = 0.35


@dataclass
class Detection:
    label: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    mask_area_px: float | None = None
    area_method: str | None = None
    category: str | None = None
    area_px_used: float | None = None
    estimated_weight_kg: float | None = None
    expected_weight_min_kg: float | None = None
    expected_weight_max_kg: float | None = None
    weight_method: str | None = None

    @property
    def box_area_px(self) -> float:
        x1, y1, x2, y2 = self.box_xyxy
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["box_area_px"] = self.box_area_px
        return data


@dataclass
class ImageResult:
    image_path: str
    annotated_path: str | None
    detections: list[Detection] = field(default_factory=list)
    total_weight_kg: float = 0.0
    expected_weight_min_kg: float = 0.0
    expected_weight_max_kg: float = 0.0
    totals_by_material_kg: dict[str, float] = field(default_factory=dict)
    totals_by_category_kg: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "annotated_path": self.annotated_path,
            "total_weight_kg": self.total_weight_kg,
            "expected_weight_min_kg": self.expected_weight_min_kg,
            "expected_weight_max_kg": self.expected_weight_max_kg,
            "totals_by_material_kg": self.totals_by_material_kg,
            "totals_by_category_kg": self.totals_by_category_kg,
            "detections": [d.to_dict() for d in self.detections],
        }


@dataclass
class PileSummary:
    aggregation: str
    image_count: int
    aggregate_total_weight_kg: float
    expected_weight_min_kg: float
    expected_weight_max_kg: float
    aggregate_by_material_kg: dict[str, float]
    aggregate_by_category_kg: dict[str, float]
    images: list[ImageResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregation": self.aggregation,
            "image_count": self.image_count,
            "aggregate_total_weight_kg": self.aggregate_total_weight_kg,
            "expected_weight_min_kg": self.expected_weight_min_kg,
            "expected_weight_max_kg": self.expected_weight_max_kg,
            "aggregate_by_material_kg": self.aggregate_by_material_kg,
            "aggregate_by_category_kg": self.aggregate_by_category_kg,
            "images": [image.to_dict() for image in self.images],
        }
