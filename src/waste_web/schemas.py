from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DetectionResponse(BaseModel):
    label: str
    class_id: int
    confidence: float
    box_xyxy: list[float]
    category: str | None = None
    area_px_used: float | None = None
    estimated_weight_kg: float | None = None
    expected_weight_min_kg: float | None = None
    expected_weight_max_kg: float | None = None
    weight_method: str | None = None


class ImageResultResponse(BaseModel):
    image_id: int
    filename: str
    width: int
    height: int
    input_url: str
    output_url: str
    detection_count: int
    mean_confidence: float | None
    estimated_weight_kg: float
    expected_weight_min_kg: float
    expected_weight_max_kg: float
    totals_by_material_kg: dict[str, float]
    detections: list[DetectionResponse]


class PredictionRunResponse(BaseModel):
    run_id: str
    created_at: datetime
    confidence_threshold: float
    duration_ms: int
    total_detections: int
    estimated_weight_kg: float
    expected_weight_min_kg: float
    expected_weight_max_kg: float
    weight_aggregation: str
    pixel_area_cm2: float
    images: list[ImageResultResponse]


class HealthResponse(BaseModel):
    status: str
    model_ready: bool
    device: str
    model_name: str
    class_count: int
    input_size: int
    model_error: str | None = None


class AuditRunSummary(BaseModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: str
    image_count: int
    total_detections: int
    confidence_threshold: float
    duration_ms: int | None


class AuditRunDetail(AuditRunSummary):
    model_path: str
    device: str
    error_message: str | None
    images: list[ImageResultResponse] = Field(default_factory=list)
