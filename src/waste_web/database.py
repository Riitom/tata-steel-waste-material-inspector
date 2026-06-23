from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


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

    run: Mapped[InferenceRun] = relationship(back_populates="images")

    @property
    def detections(self) -> list[dict[str, Any]]:
        return json.loads(self.detections_json)


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

    def create_run(
        self,
        run_id: str,
        model_path: str,
        device: str,
        confidence_threshold: float,
        image_count: int,
    ) -> InferenceRun:
        with self.session_factory() as session:
            run = InferenceRun(
                id=run_id,
                model_path=model_path,
                device=device,
                confidence_threshold=confidence_threshold,
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
            statement = select(InferenceRun).order_by(InferenceRun.created_at.desc()).offset(offset).limit(limit)
            return list(session.scalars(statement))

    def get_run(self, run_id: str) -> InferenceRun | None:
        with self.session_factory() as session:
            statement = select(InferenceRun).where(InferenceRun.id == run_id)
            run = session.scalar(statement)
            if run is not None:
                _ = list(run.images)
            return run

    def get_image(self, image_id: int) -> AuditImage | None:
        with self.session_factory() as session:
            return session.get(AuditImage, image_id)

    def session(self) -> Session:
        return self.session_factory()

    def close(self) -> None:
        self.engine.dispose()
