from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value: str, default: str) -> Path:
    candidate = Path(value or default)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    model_path: Path = resolve_project_path(
        os.getenv("WASTE_MODEL_PATH", ""),
        "models/final.pt",
    )
    dataset_config_path: Path = resolve_project_path(
        os.getenv("WASTE_DATASET_CONFIG", os.getenv("WASTE_ANNOTATION_PATH", "")),
        "configs/full_dataset_yolo.yaml",
    )
    materials_path: Path = resolve_project_path(
        os.getenv("WASTE_MATERIALS_PATH", ""),
        "configs/materials.yaml",
    )
    data_dir: Path = resolve_project_path(os.getenv("WASTE_DATA_DIR", ""), "data")
    frontend_dist: Path = resolve_project_path(os.getenv("WASTE_FRONTEND_DIST", ""), "web/frontend/dist")
    audit_key: str = os.getenv("WASTE_AUDIT_KEY", "")
    device: str = os.getenv("WASTE_DEVICE", "")
    model_imgsz: int = int(os.getenv("WASTE_MODEL_IMGSZ", "640"))
    default_pixel_area_cm2: float = float(os.getenv("WASTE_PIXEL_AREA_CM2", "0.05"))
    max_files: int = int(os.getenv("WASTE_MAX_FILES", "12"))
    max_file_bytes: int = int(os.getenv("WASTE_MAX_FILE_MB", "20")) * 1024 * 1024
    quality_min_dimension: int = int(os.getenv("WASTE_QUALITY_MIN_DIMENSION", "240"))
    quality_min_blur: float = float(os.getenv("WASTE_QUALITY_MIN_BLUR", "20"))
    quality_min_contrast: float = float(os.getenv("WASTE_QUALITY_MIN_CONTRAST", "10"))
    quality_min_brightness: float = float(os.getenv("WASTE_QUALITY_MIN_BRIGHTNESS", "12"))
    quality_max_brightness: float = float(os.getenv("WASTE_QUALITY_MAX_BRIGHTNESS", "245"))

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"

    @property
    def database_path(self) -> Path:
        return self.audit_dir / "audit.db"

    def ensure_directories(self) -> None:
        for path in (self.uploads_dir, self.outputs_dir, self.audit_dir):
            path.mkdir(parents=True, exist_ok=True)
