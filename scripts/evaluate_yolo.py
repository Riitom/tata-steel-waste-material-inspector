from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate an Ultralytics YOLO material detector.")
    parser.add_argument("--model", default="models/final.pt")
    parser.add_argument("--data", default="configs/full_dataset_yolo.yaml")
    parser.add_argument("--split", choices=["val", "test"], default="test")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--conf", type=float, default=0.001)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--project", default="runs")
    parser.add_argument("--name", default="yolo_eval")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from ultralytics import YOLO

    model_path = resolve_path(args.model)
    data_path = resolve_path(args.data)
    project_path = resolve_path(args.project)
    model = YOLO(str(model_path))
    metrics = model.val(
        data=str(data_path),
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        conf=args.conf,
        iou=args.iou,
        project=str(project_path),
        name=args.name,
        save_json=True,
        exist_ok=True,
    )
    save_dir = Path(getattr(metrics, "save_dir", project_path / args.name))
    payload = getattr(metrics, "results_dict", {})
    (save_dir / "metrics_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"YOLO_EVAL_DIR={save_dir}")
    print("YOLO_EVAL_PASS")


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


if __name__ == "__main__":
    main()
