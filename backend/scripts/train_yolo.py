from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an Ultralytics YOLO detector for material detection.")
    parser.add_argument("--data", default="configs/full_dataset_box.yaml", help="Ultralytics data YAML.")
    parser.add_argument("--model", default="yolo26x.pt", help="YOLO detection base model or checkpoint.")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--project", default=".")
    parser.add_argument("--name", default="models")
    parser.add_argument("--final-model", default="models/final.pt", help="Clean final checkpoint path to copy best.pt into.")
    parser.add_argument(
        "--target-epoch",
        type=int,
        default=None,
        help="Stop cleanly after this absolute epoch number, including when resuming.",
    )
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--lr0", type=float, default=0.01)
    parser.add_argument("--optimizer", default="auto")
    parser.add_argument("--mosaic", type=float, default=None, help="Override mosaic augmentation strength.")
    parser.add_argument("--erasing", type=float, default=None, help="Override random erasing augmentation strength.")
    parser.add_argument("--close-mosaic", type=int, default=None, help="Override Ultralytics close_mosaic setting.")
    parser.add_argument(
        "--warmup-epochs",
        type=float,
        default=None,
        help="Override Ultralytics warmup epochs. Use a small value when continuing from a trained checkpoint.",
    )
    parser.add_argument("--cos-lr", action="store_true", help="Use cosine learning-rate scheduling.")
    parser.add_argument("--cache", action="store_true", help="Cache images. Avoid for very large Open Images runs.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from ultralytics import YOLO

    data_path = resolve_path(args.data)
    project_path = resolve_path(args.project)
    final_model_path = resolve_path(args.final_model)
    model_path = resolve_path(args.model)
    model = YOLO(str(model_path) if model_path.exists() else args.model)
    model.add_callback("on_fit_epoch_end", print_epoch_metrics)
    if args.target_epoch is not None:
        if args.target_epoch < 1:
            raise SystemExit("--target-epoch must be at least 1.")

        def stop_at_target_epoch(trainer) -> None:
            completed_epoch = trainer.epoch + 1
            if completed_epoch >= args.target_epoch:
                print(f"YOLO_TARGET_EPOCH_REACHED={completed_epoch}", flush=True)
                trainer.stop = True

        model.add_callback("on_train_epoch_end", stop_at_target_epoch)

    train_kwargs = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "device": args.device,
        "project": str(project_path),
        "name": args.name,
        "patience": args.patience,
        "lr0": args.lr0,
        "optimizer": args.optimizer,
        "cos_lr": args.cos_lr,
        "cache": args.cache,
        "resume": args.resume,
        "amp": args.amp,
        "exist_ok": True,
        "plots": True,
    }
    if args.warmup_epochs is not None:
        train_kwargs["warmup_epochs"] = args.warmup_epochs
    if args.mosaic is not None:
        train_kwargs["mosaic"] = args.mosaic
    if args.erasing is not None:
        train_kwargs["erasing"] = args.erasing
    if args.close_mosaic is not None:
        train_kwargs["close_mosaic"] = args.close_mosaic

    results = model.train(**train_kwargs)
    save_dir = Path(getattr(results, "save_dir", project_path / args.name))
    best_model_path = save_dir / "weights" / "best.pt"
    if not best_model_path.exists():
        raise SystemExit(f"YOLO best checkpoint was not created: {best_model_path}")
    final_model_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_model_path, final_model_path)
    print(f"YOLO_RUN_DIR={save_dir}")
    print(f"YOLO_MODEL_BEST={best_model_path}")
    print(f"YOLO_MODEL_FINAL={final_model_path}")
    print("YOLO_TRAIN_PASS")


def print_epoch_metrics(trainer) -> None:
    metrics = getattr(trainer, "metrics", {}) or {}
    epoch = int(getattr(trainer, "epoch", -1)) + 1
    values = {
        "precision": read_metric(metrics, "metrics/precision(B)", "metrics/precision"),
        "recall": read_metric(metrics, "metrics/recall(B)", "metrics/recall"),
        "mAP50": read_metric(metrics, "metrics/mAP50(B)", "metrics/mAP50"),
        "mAP50_95": read_metric(metrics, "metrics/mAP50-95(B)", "metrics/mAP50-95"),
    }
    print(
        "YOLO_EPOCH_METRICS "
        f"epoch={epoch} "
        f"precision={format_metric(values['precision'])} "
        f"recall={format_metric(values['recall'])} "
        f"mAP50={format_metric(values['mAP50'])} "
        f"mAP50_95={format_metric(values['mAP50_95'])}",
        flush=True,
    )


def read_metric(metrics: dict, *keys: str) -> float | None:
    for key in keys:
        value = metrics.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def format_metric(value: float | None) -> str:
    if value is None or value != value:
        return "nan"
    return f"{value:.5f}"


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


if __name__ == "__main__":
    main()


