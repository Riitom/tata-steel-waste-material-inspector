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
    parser.add_argument("--data", default="configs/full_dataset_yolo.yaml", help="Ultralytics data YAML.")
    parser.add_argument("--model", default="yolo26x.pt", help="YOLO base model or checkpoint.")
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
    model = YOLO(args.model)
    if args.target_epoch is not None:
        if args.target_epoch < 1:
            raise SystemExit("--target-epoch must be at least 1.")

        def stop_at_target_epoch(trainer) -> None:
            completed_epoch = trainer.epoch + 1
            if completed_epoch >= args.target_epoch:
                print(f"YOLO_TARGET_EPOCH_REACHED={completed_epoch}", flush=True)
                trainer.stop = True

        model.add_callback("on_train_epoch_end", stop_at_target_epoch)

    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        project=str(project_path),
        name=args.name,
        patience=args.patience,
        lr0=args.lr0,
        optimizer=args.optimizer,
        cache=args.cache,
        resume=args.resume,
        amp=args.amp,
        exist_ok=True,
        plots=True,
    )
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


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


if __name__ == "__main__":
    main()
