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
    area_refinement_reliability: float | None = None
    estimated_weight_kg: float | None = None
    expected_weight_min_kg: float | None = None
    expected_weight_max_kg: float | None = None
    weight_method: str | None = None


class ImageQualityResponse(BaseModel):
    valid: bool
    score: float
    blur_score: float
    contrast_score: float
    brightness: float
    width: int
    height: int
    issues: list[str] = Field(default_factory=list)


class ImageResultResponse(BaseModel):
    image_id: int
    filename: str
    width: int
    height: int
    input_url: str | None
    output_url: str | None
    detection_count: int
    mean_confidence: float | None
    estimated_weight_kg: float
    expected_weight_min_kg: float
    expected_weight_max_kg: float
    totals_by_material_kg: dict[str, float]
    quality: ImageQualityResponse | None = None
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
    source_run_id: str | None = None
    images: list[ImageResultResponse]


class HealthResponse(BaseModel):
    status: str
    model_ready: bool
    device: str
    model_name: str
    class_count: int
    input_size: int
    model_error: str | None = None


class DashboardDailyActivity(BaseModel):
    date: str
    label: str
    runs: int
    images: int
    detections: int


class DashboardMaterialCount(BaseModel):
    label: str
    count: int


class DashboardSummary(BaseModel):
    generated_at: datetime
    timezone: str
    today_label: str
    total_runs: int
    today_runs: int
    completed_runs: int
    failed_runs: int
    total_images: int
    today_images: int
    total_detections: int
    today_detections: int
    success_rate: float
    average_duration_ms: int | None
    daily_activity: list[DashboardDailyActivity] = Field(default_factory=list)
    material_counts: list[DashboardMaterialCount] = Field(default_factory=list)


class AuditRunSummary(BaseModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    status: str
    image_count: int
    total_detections: int
    confidence_threshold: float
    duration_ms: int | None


class HistoryRunSummary(AuditRunSummary):
    source_run_id: str | None = None
    pixel_area_cm2: float | None = None
    preview_input_url: str | None = None
    preview_output_url: str | None = None
    preview_filename: str | None = None
    mean_confidence: float | None = None
    expected_weight_min_kg: float = 0.0
    expected_weight_max_kg: float = 0.0


class AuditRunDetail(AuditRunSummary):
    model_path: str
    device: str
    error_message: str | None
    source_run_id: str | None = None
    pixel_area_cm2: float | None = None
    expected_weight_min_kg: float = 0.0
    expected_weight_max_kg: float = 0.0
    images: list[ImageResultResponse] = Field(default_factory=list)
