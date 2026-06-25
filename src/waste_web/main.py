from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import statistics
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from waste_detector.config import load_material_profiles
from waste_detector.estimator import WeightEstimator
from waste_detector.types import Detection

from .database import AuditImage, AuditStore, InferenceRun
from .inference import YoloInferenceService
from .schemas import (
    AuditRunDetail,
    AuditRunSummary,
    DashboardSummary,
    HealthResponse,
    HistoryRunSummary,
    ImageResultResponse,
    PredictionRunResponse,
)
from .settings import Settings
from .quality import ImageQualityChecker, ImageQualityResult


settings = Settings()
store = AuditStore(settings.database_path)
inference = YoloInferenceService(settings)
material_profiles = load_material_profiles(settings.materials_path)
quality_checker = ImageQualityChecker(
    minimum_dimension=settings.quality_min_dimension,
    minimum_blur_score=settings.quality_min_blur,
    minimum_contrast=settings.quality_min_contrast,
    minimum_brightness=settings.quality_min_brightness,
    maximum_brightness=settings.quality_max_brightness,
)


@dataclass
class PreparedImage:
    raw: bytes
    image: Image.Image
    original_name: str
    mime_type: str
    quality: ImageQualityResult


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    store.initialize()
    try:
        await run_in_threadpool(inference.load)
    except Exception as exc:
        inference.load_error = str(exc)
    try:
        yield
    finally:
        store.close()


app = FastAPI(
    title="Waste Material Inspector",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    status = "ready" if inference.ready else "missing_model" if inference.load_error else "loading"
    return HealthResponse(
        status=status,
        model_ready=inference.ready,
        device=str(inference.device),
        model_name=settings.model_path.name,
        class_count=len(inference.class_names),
        input_size=settings.model_imgsz,
        model_error=inference.load_error,
    )


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    return DashboardSummary(**store.dashboard_summary())


@app.post("/api/predict", response_model=PredictionRunResponse)
async def predict(
    files: list[UploadFile] = File(...),
    confidence: float = Form(0.6),
    max_detections: int = Form(50),
    pixel_area_cm2: float = Form(settings.default_pixel_area_cm2),
) -> PredictionRunResponse:
    validate_prediction_parameters(
        files_count=len(files),
        confidence=confidence,
        max_detections=max_detections,
        pixel_area_cm2=pixel_area_cm2,
    )
    prepared = await prepare_uploads(files)
    return await execute_prediction(
        prepared,
        confidence=confidence,
        max_detections=max_detections,
        pixel_area_cm2=pixel_area_cm2,
    )


def validate_prediction_parameters(
    files_count: int,
    confidence: float,
    max_detections: int,
    pixel_area_cm2: float,
) -> None:
    if files_count < 1:
        raise HTTPException(status_code=400, detail="Select at least one image.")
    if files_count > settings.max_files:
        raise HTTPException(status_code=400, detail=f"Upload at most {settings.max_files} images per run.")
    if not 0.05 <= confidence <= 0.95:
        raise HTTPException(status_code=400, detail="Confidence must be between 0.05 and 0.95.")
    if not 1 <= max_detections <= 200:
        raise HTTPException(status_code=400, detail="max_detections must be between 1 and 200.")
    if not 0.000001 <= pixel_area_cm2 <= 100:
        raise HTTPException(status_code=400, detail="Pixel area must be between 0.000001 and 100 cm2.")
    if not inference.ready:
        raise HTTPException(status_code=503, detail=inference.load_error or "YOLO model is not loaded.")


async def prepare_uploads(files: list[UploadFile]) -> list[PreparedImage]:
    prepared = []
    quality_failures = []
    for index, upload in enumerate(files, start=1):
        raw = await upload.read()
        prepared_image = prepare_image_bytes(
            raw,
            original_name=Path(upload.filename or f"image_{index}.jpg").name,
            mime_type=upload.content_type or "image/jpeg",
        )
        prepared.append(prepared_image)
        if not prepared_image.quality.valid:
            quality_failures.append(
                {
                    "filename": prepared_image.original_name,
                    "score": prepared_image.quality.score,
                    "issues": prepared_image.quality.issues,
                }
            )
    if quality_failures:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "image_quality_failed",
                "message": (
                    "Detection was not started because one or more images are "
                    "not suitable for reliable analysis."
                ),
                "images": quality_failures,
            },
        )
    return prepared


def prepare_image_bytes(raw: bytes, original_name: str, mime_type: str) -> PreparedImage:
    if len(raw) > settings.max_file_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"{original_name} exceeds the file-size limit.",
        )
    if not raw:
        raise HTTPException(status_code=400, detail=f"{original_name} is empty.")
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{original_name} is not a valid image.",
        ) from exc
    return PreparedImage(
        raw=raw,
        image=image,
        original_name=original_name,
        mime_type=mime_type,
        quality=quality_checker.assess(image),
    )


async def execute_prediction(
    prepared: list[PreparedImage],
    confidence: float,
    max_detections: int,
    pixel_area_cm2: float,
    source_run_id: str | None = None,
) -> PredictionRunResponse:
    run_id = str(uuid.uuid4())
    started = time.perf_counter()
    weight_estimator = WeightEstimator(material_profiles, pixel_area_cm2=pixel_area_cm2)
    store.create_run(
        run_id=run_id,
        model_path=str(settings.model_path),
        device=str(inference.device),
        confidence_threshold=confidence,
        image_count=len(prepared),
        pixel_area_cm2=pixel_area_cm2,
        source_run_id=source_run_id,
    )
    input_dir = settings.uploads_dir / run_id
    output_dir = settings.outputs_dir / run_id
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    response_images = []
    total_detections = 0
    try:
        for index, prepared_image in enumerate(prepared, start=1):
            raw = prepared_image.raw
            image = prepared_image.image
            original_name = prepared_image.original_name
            safe_stem = sanitize_name(Path(original_name).stem) or f"image_{index}"
            stored_name = f"{index:02d}_{safe_stem}.jpg"
            input_path = input_dir / stored_name
            output_path = output_dir / f"{Path(stored_name).stem}_detected.jpg"
            image.save(input_path, format="JPEG", quality=95)

            detections, annotated = await run_in_threadpool(
                inference.predict,
                image,
                confidence,
                max_detections,
            )
            (
                detections,
                image_weight,
                image_weight_min,
                image_weight_max,
                totals_by_material,
            ) = add_weight_estimates(
                detections,
                weight_estimator,
            )
            annotated = inference.draw_predictions(image, detections)
            annotated.save(output_path, format="JPEG", quality=95)
            mean_confidence = (
                sum(item["confidence"] for item in detections) / len(detections)
                if detections
                else None
            )
            audit_image = store.add_image(
                run_id,
                original_filename=original_name,
                stored_filename=stored_name,
                input_path=str(input_path.relative_to(settings.data_dir)),
                output_path=str(output_path.relative_to(settings.data_dir)),
                mime_type=prepared_image.mime_type,
                file_size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                width=image.width,
                height=image.height,
                detection_count=len(detections),
                mean_confidence=mean_confidence,
                detections_json=json.dumps(detections),
                quality_json=json.dumps(prepared_image.quality.to_dict()),
            )
            total_detections += len(detections)
            response_images.append(
                image_response(
                    run_id,
                    audit_image,
                    estimated_weight_kg=image_weight,
                    expected_weight_min_kg=image_weight_min,
                    expected_weight_max_kg=image_weight_max,
                    totals_by_material_kg=totals_by_material,
                )
            )

        duration_ms = round((time.perf_counter() - started) * 1000)
        estimated_weight_kg = (
            statistics.mean(image.estimated_weight_kg for image in response_images)
            if response_images
            else 0.0
        )
        expected_weight_min_kg = (
            statistics.mean(image.expected_weight_min_kg for image in response_images)
            if response_images
            else 0.0
        )
        expected_weight_max_kg = (
            statistics.mean(image.expected_weight_max_kg for image in response_images)
            if response_images
            else 0.0
        )
        store.finish_run(run_id, total_detections=total_detections, duration_ms=duration_ms)
        run = store.get_run(run_id)
        if run is None:
            raise RuntimeError("The completed audit run could not be loaded.")
        return PredictionRunResponse(
            run_id=run_id,
            created_at=run.created_at,
            confidence_threshold=confidence,
            duration_ms=duration_ms,
            total_detections=total_detections,
            estimated_weight_kg=estimated_weight_kg,
            expected_weight_min_kg=expected_weight_min_kg,
            expected_weight_max_kg=expected_weight_max_kg,
            weight_aggregation="mean",
            pixel_area_cm2=pixel_area_cm2,
            source_run_id=source_run_id,
            images=response_images,
        )
    except ValueError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000)
        store.fail_run(run_id, str(exc), duration_ms)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000)
        store.fail_run(run_id, str(exc), duration_ms)
        raise HTTPException(status_code=500, detail="Inference failed. Check the server log.") from exc


@app.get("/api/history/runs", response_model=list[HistoryRunSummary])
def history_runs(limit: int = 50, offset: int = 0) -> list[HistoryRunSummary]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    return [history_summary(run) for run in store.list_runs(limit=limit, offset=offset)]


@app.get("/api/history/runs/{run_id}", response_model=AuditRunDetail)
def history_run(run_id: str) -> AuditRunDetail:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Inspection run not found.")
    return run_detail(run)


@app.post("/api/history/runs/{run_id}/rerun", response_model=PredictionRunResponse)
async def rerun_history(
    run_id: str,
    confidence: float | None = Form(default=None),
    max_detections: int = Form(50),
    pixel_area_cm2: float | None = Form(default=None),
) -> PredictionRunResponse:
    source = store.get_run(run_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Inspection run not found.")
    if not source.images:
        raise HTTPException(status_code=400, detail="This run has no stored input images.")

    resolved_confidence = confidence if confidence is not None else source.confidence_threshold
    resolved_pixel_area = (
        pixel_area_cm2
        if pixel_area_cm2 is not None
        else source.pixel_area_cm2 or settings.default_pixel_area_cm2
    )
    validate_prediction_parameters(
        files_count=len(source.images),
        confidence=resolved_confidence,
        max_detections=max_detections,
        pixel_area_cm2=resolved_pixel_area,
    )

    prepared = []
    quality_failures = []
    for image_record in source.images:
        path = safe_data_path(image_record.input_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Original file for {image_record.original_filename} is no longer "
                    "available, so this inspection cannot be rerun."
                ),
            )
        raw = path.read_bytes()
        item = prepare_image_bytes(
            raw,
            original_name=image_record.original_filename,
            mime_type=image_record.mime_type,
        )
        prepared.append(item)
        if not item.quality.valid:
            quality_failures.append(
                {
                    "filename": item.original_name,
                    "score": item.quality.score,
                    "issues": item.quality.issues,
                }
            )
    if quality_failures:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "image_quality_failed",
                "message": "Stored images no longer pass the current quality requirements.",
                "images": quality_failures,
            },
        )
    return await execute_prediction(
        prepared,
        confidence=resolved_confidence,
        max_detections=max_detections,
        pixel_area_cm2=resolved_pixel_area,
        source_run_id=run_id,
    )


@app.get("/api/files/{run_id}/{image_id}/{kind}", include_in_schema=False)
def result_file(run_id: str, image_id: int, kind: str) -> FileResponse:
    image = store.get_image(image_id)
    if image is None or image.run_id != run_id:
        raise HTTPException(status_code=404, detail="Image record not found.")
    relative_path = image.input_path if kind == "input" else image.output_path if kind == "output" else None
    if relative_path is None:
        raise HTTPException(status_code=404, detail="File type not found.")
    path = safe_data_path(relative_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")
    return FileResponse(path)


def require_audit_key(x_audit_key: str | None = Header(default=None)) -> None:
    if not settings.audit_key:
        raise HTTPException(
            status_code=503,
            detail="Auditor API is disabled. Set WASTE_AUDIT_KEY before starting the server.",
        )
    if x_audit_key is None or not secrets.compare_digest(x_audit_key, settings.audit_key):
        raise HTTPException(status_code=401, detail="Invalid auditor key.")


@app.get(
    "/api/audit/runs",
    response_model=list[AuditRunSummary],
    dependencies=[Depends(require_audit_key)],
)
def audit_runs(limit: int = 50, offset: int = 0) -> list[AuditRunSummary]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    return [run_summary(run) for run in store.list_runs(limit=limit, offset=offset)]


@app.get(
    "/api/audit/runs/{run_id}",
    response_model=AuditRunDetail,
    dependencies=[Depends(require_audit_key)],
)
def audit_run(run_id: str) -> AuditRunDetail:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found.")
    return run_detail(run)


def sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:80]


def safe_data_path(relative_path: str) -> Path:
    candidate = (settings.data_dir / relative_path).resolve()
    data_root = settings.data_dir.resolve()
    if candidate != data_root and data_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid stored path.")
    return candidate


def stored_file_url(run_id: str, image: AuditImage, kind: str) -> str | None:
    relative_path = (
        image.input_path
        if kind == "input"
        else image.output_path
        if kind == "output"
        else None
    )
    if relative_path is None:
        return None
    try:
        path = safe_data_path(relative_path)
    except HTTPException:
        return None
    if not path.exists() or not path.is_file():
        return None
    return f"/api/files/{run_id}/{image.id}/{kind}"


def image_response(
    run_id: str,
    image: AuditImage,
    estimated_weight_kg: float | None = None,
    expected_weight_min_kg: float | None = None,
    expected_weight_max_kg: float | None = None,
    totals_by_material_kg: dict[str, float] | None = None,
) -> ImageResultResponse:
    detections = image.detections
    if estimated_weight_kg is None:
        estimated_weight_kg = sum(float(item.get("estimated_weight_kg") or 0.0) for item in detections)
    if expected_weight_min_kg is None or expected_weight_max_kg is None:
        ranges = [detection_weight_range(item) for item in detections]
        expected_weight_min_kg = sum(weight_min for weight_min, _ in ranges)
        expected_weight_max_kg = sum(weight_max for _, weight_max in ranges)
    if totals_by_material_kg is None:
        totals_by_material_kg = {}
        for item in detections:
            label = str(item["label"])
            totals_by_material_kg[label] = totals_by_material_kg.get(label, 0.0) + float(
                item.get("estimated_weight_kg") or 0.0
            )
    return ImageResultResponse(
        image_id=image.id,
        filename=image.original_filename,
        width=image.width,
        height=image.height,
        input_url=stored_file_url(run_id, image, "input"),
        output_url=stored_file_url(run_id, image, "output"),
        detection_count=image.detection_count,
        mean_confidence=image.mean_confidence,
        estimated_weight_kg=estimated_weight_kg,
        expected_weight_min_kg=expected_weight_min_kg,
        expected_weight_max_kg=expected_weight_max_kg,
        totals_by_material_kg=totals_by_material_kg,
        quality=image.quality,
        detections=detections,
    )


def add_weight_estimates(
    detections: list[dict],
    estimator: WeightEstimator,
) -> tuple[list[dict], float, float, float, dict[str, float]]:
    enriched = []
    totals_by_material: dict[str, float] = {}
    expected_min = 0.0
    expected_max = 0.0
    for item in detections:
        label = str(item["label"])
        estimated = estimator.estimate_detection(
            Detection(
                label=label,
                confidence=float(item["confidence"]),
                box_xyxy=tuple(float(value) for value in item["box_xyxy"]),
            )
        )
        weight = float(estimated.estimated_weight_kg or 0.0)
        weight_min = float(estimated.expected_weight_min_kg or 0.0)
        weight_max = float(estimated.expected_weight_max_kg or 0.0)
        totals_by_material[estimated.label] = totals_by_material.get(estimated.label, 0.0) + weight
        expected_min += weight_min
        expected_max += weight_max
        enriched.append(
            {
                **item,
                "category": estimated.category,
                "area_method": estimated.area_method,
                "box_area_px": round(float(estimated.box_area_px), 4),
                "area_px_used": round(float(estimated.area_px_used or 0.0), 4),
                "estimated_weight_kg": round(weight, 6),
                "expected_weight_min_kg": round(weight_min, 6),
                "expected_weight_max_kg": round(weight_max, 6),
                "weight_method": estimated.weight_method,
                "box_fill_ratio_used": estimated.box_fill_ratio_used,
                "thickness_cm_used": estimated.thickness_cm_used,
                "density_kg_m3_used": estimated.density_kg_m3_used,
                "pixel_area_cm2_used": estimated.pixel_area_cm2_used,
            }
        )
    return (
        enriched,
        sum(totals_by_material.values()),
        expected_min,
        expected_max,
        totals_by_material,
    )


def detection_weight_range(detection: dict) -> tuple[float, float]:
    midpoint = float(detection.get("estimated_weight_kg") or 0.0)
    weight_min = float(detection.get("expected_weight_min_kg", midpoint) or 0.0)
    weight_max = float(detection.get("expected_weight_max_kg", midpoint) or 0.0)
    return weight_min, weight_max


def run_summary(run: InferenceRun) -> AuditRunSummary:
    return AuditRunSummary(
        run_id=run.id,
        created_at=run.created_at,
        completed_at=run.completed_at,
        status=run.status,
        image_count=run.image_count,
        total_detections=run.total_detections,
        confidence_threshold=run.confidence_threshold,
        duration_ms=run.duration_ms,
    )


def history_summary(run: InferenceRun) -> HistoryRunSummary:
    first_image = run.images[0] if run.images else None
    weight_min, weight_max = run_weight_range(run)
    confidences = [
        image.mean_confidence
        for image in run.images
        if image.mean_confidence is not None
    ]
    return HistoryRunSummary(
        **run_summary(run).model_dump(),
        source_run_id=run.source_run_id,
        pixel_area_cm2=run.pixel_area_cm2,
        preview_input_url=stored_file_url(run.id, first_image, "input") if first_image else None,
        preview_output_url=stored_file_url(run.id, first_image, "output") if first_image else None,
        preview_filename=first_image.original_filename if first_image is not None else None,
        mean_confidence=statistics.mean(confidences) if confidences else None,
        expected_weight_min_kg=weight_min,
        expected_weight_max_kg=weight_max,
    )


def run_detail(run: InferenceRun) -> AuditRunDetail:
    weight_min, weight_max = run_weight_range(run)
    return AuditRunDetail(
        **run_summary(run).model_dump(),
        model_path=run.model_path,
        device=run.device,
        error_message=run.error_message,
        source_run_id=run.source_run_id,
        pixel_area_cm2=run.pixel_area_cm2,
        expected_weight_min_kg=weight_min,
        expected_weight_max_kg=weight_max,
        images=[image_response(run.id, image) for image in run.images],
    )


def run_weight_range(run: InferenceRun) -> tuple[float, float]:
    ranges = [
        image_weight_range(image)
        for image in run.images
    ]
    if not ranges:
        return 0.0, 0.0
    return (
        statistics.mean(weight_min for weight_min, _ in ranges),
        statistics.mean(weight_max for _, weight_max in ranges),
    )


def image_weight_range(image: AuditImage) -> tuple[float, float]:
    ranges = [detection_weight_range(item) for item in image.detections]
    return (
        sum(weight_min for weight_min, _ in ranges),
        sum(weight_max for _, weight_max in ranges),
    )


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    index = settings.frontend_dist / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend is not built. Run npm install and npm run build in web/frontend.",
        )
    return FileResponse(index)


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_files(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")
    candidate = (settings.frontend_dist / full_path).resolve()
    frontend_root = settings.frontend_dist.resolve()
    if candidate.exists() and candidate.is_file() and frontend_root in candidate.parents:
        return FileResponse(candidate)
    index = settings.frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend is not built.")
