from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload, sessionmaker


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class InferenceRun(Base):
    __tablename__ = "inference_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="processing", index=True)
    model_path: Mapped[str] = mapped_column(Text)
    device: Mapped[str] = mapped_column(String(32))
    confidence_threshold: Mapped[float] = mapped_column(Float)
    pixel_area_cm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    total_detections: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    images: Mapped[list["AuditImage"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AuditImage.id",
    )


class AuditImage(Base):
    __tablename__ = "audit_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("inference_runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    original_filename: Mapped[str] = mapped_column(Text)
    stored_filename: Mapped[str] = mapped_column(Text)
    input_path: Mapped[str] = mapped_column(Text)
    output_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    detection_count: Mapped[int] = mapped_column(Integer)
    mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    detections_json: Mapped[str] = mapped_column(Text)
    quality_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[InferenceRun] = relationship(back_populates="images")

    @property
    def detections(self) -> list[dict[str, Any]]:
        return json.loads(self.detections_json)

    @property
    def quality(self) -> dict[str, Any] | None:
        if not self.quality_json:
            return None
        return json.loads(self.quality_json)


class AuditStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        schema = inspect(self.engine)
        run_columns = {column["name"] for column in schema.get_columns("inference_runs")}
        image_columns = {column["name"] for column in schema.get_columns("audit_images")}
        with self.engine.begin() as connection:
            if "pixel_area_cm2" not in run_columns:
                connection.execute(text("ALTER TABLE inference_runs ADD COLUMN pixel_area_cm2 FLOAT"))
            if "source_run_id" not in run_columns:
                connection.execute(text("ALTER TABLE inference_runs ADD COLUMN source_run_id VARCHAR(36)"))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_inference_runs_source_run_id "
                        "ON inference_runs (source_run_id)"
                    )
                )
            if "quality_json" not in image_columns:
                connection.execute(text("ALTER TABLE audit_images ADD COLUMN quality_json TEXT"))

    def create_run(
        self,
        run_id: str,
        model_path: str,
        device: str,
        confidence_threshold: float,
        image_count: int,
        pixel_area_cm2: float | None = None,
        source_run_id: str | None = None,
    ) -> InferenceRun:
        with self.session_factory() as session:
            run = InferenceRun(
                id=run_id,
                model_path=model_path,
                device=device,
                confidence_threshold=confidence_threshold,
                pixel_area_cm2=pixel_area_cm2,
                source_run_id=source_run_id,
                image_count=image_count,
            )
            session.add(run)
            session.commit()
            return run

    def add_image(self, run_id: str, **values: Any) -> AuditImage:
        with self.session_factory() as session:
            image = AuditImage(run_id=run_id, **values)
            session.add(image)
            session.commit()
            return image

    def finish_run(self, run_id: str, total_detections: int, duration_ms: int) -> None:
        with self.session_factory() as session:
            run = session.get(InferenceRun, run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = "completed"
            run.completed_at = utc_now()
            run.total_detections = total_detections
            run.duration_ms = duration_ms
            session.commit()

    def fail_run(self, run_id: str, error_message: str, duration_ms: int) -> None:
        with self.session_factory() as session:
            run = session.get(InferenceRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.completed_at = utc_now()
            run.error_message = error_message
            run.duration_ms = duration_ms
            session.commit()

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[InferenceRun]:
        with self.session_factory() as session:
            statement = (
                select(InferenceRun)
                .options(selectinload(InferenceRun.images))
                .order_by(InferenceRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.scalars(statement))

    def get_run(self, run_id: str) -> InferenceRun | None:
        with self.session_factory() as session:
            statement = (
                select(InferenceRun)
                .options(selectinload(InferenceRun.images))
                .where(InferenceRun.id == run_id)
            )
            run = session.scalar(statement)
            return run

    def get_image(self, image_id: int) -> AuditImage | None:
        with self.session_factory() as session:
            return session.get(AuditImage, image_id)

    def dashboard_summary(
        self,
        timezone_name: str = "Asia/Kolkata",
        days: int = 7,
    ) -> dict[str, Any]:
        zone = ZoneInfo(timezone_name)
        now_local = datetime.now(zone)
        today = now_local.date()
        first_day = today - timedelta(days=max(1, days) - 1)

        with self.session_factory() as session:
            runs = list(
                session.scalars(
                    select(InferenceRun)
                    .options(selectinload(InferenceRun.images))
                    .order_by(InferenceRun.created_at.asc())
                )
            )

        def local_date(value: datetime) -> date:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(zone).date()

        completed = [run for run in runs if run.status == "completed"]
        failed = [run for run in runs if run.status == "failed"]
        today_runs = [run for run in runs if local_date(run.created_at) == today]
        completed_durations = [
            run.duration_ms
            for run in completed
            if run.duration_ms is not None
        ]

        daily = {
            first_day + timedelta(days=offset): {
                "runs": 0,
                "images": 0,
                "detections": 0,
            }
            for offset in range(max(1, days))
        }
        material_counts: Counter[str] = Counter()

        for run in runs:
            run_date = local_date(run.created_at)
            if run_date in daily:
                daily[run_date]["runs"] += 1
                daily[run_date]["images"] += run.image_count
                daily[run_date]["detections"] += run.total_detections
            for image in run.images:
                for detection in image.detections:
                    label = str(detection.get("label") or "unknown")
                    material_counts[label] += 1

        total_runs = len(runs)
        return {
            "generated_at": now_local,
            "timezone": timezone_name,
            "today_label": today.isoformat(),
            "total_runs": total_runs,
            "today_runs": len(today_runs),
            "completed_runs": len(completed),
            "failed_runs": len(failed),
            "total_images": sum(run.image_count for run in runs),
            "today_images": sum(run.image_count for run in today_runs),
            "total_detections": sum(run.total_detections for run in runs),
            "today_detections": sum(run.total_detections for run in today_runs),
            "success_rate": (
                round((len(completed) / total_runs) * 100.0, 1)
                if total_runs
                else 0.0
            ),
            "average_duration_ms": (
                round(sum(completed_durations) / len(completed_durations))
                if completed_durations
                else None
            ),
            "daily_activity": [
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%a"),
                    **values,
                }
                for day, values in daily.items()
            ],
            "material_counts": [
                {"label": label, "count": count}
                for label, count in material_counts.most_common()
            ],
        }

    def session(self) -> Session:
        return self.session_factory()

    def close(self) -> None:
        self.engine.dispose()
