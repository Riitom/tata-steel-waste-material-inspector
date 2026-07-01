from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waste_web.database import AuditStore
from waste_web.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or export private inference audit records.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recent inference runs.")
    list_parser.add_argument("--limit", type=int, default=25)

    show_parser = subparsers.add_parser("show", help="Print one inference run as JSON.")
    show_parser.add_argument("run_id")

    export_parser = subparsers.add_parser("export", help="Export one run as a standalone HTML report.")
    export_parser.add_argument("run_id")
    export_parser.add_argument("--output", default=None)

    subparsers.add_parser("database", help="Print the SQLite database path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    store = AuditStore(settings.database_path)
    store.initialize()

    if args.command == "database":
        print(settings.database_path)
        return
    if args.command == "list":
        print_runs(store, args.limit)
        return

    run = store.get_run(args.run_id)
    if run is None:
        raise SystemExit(f"Audit run not found: {args.run_id}")
    if args.command == "show":
        print(json.dumps(run_payload(run), indent=2, default=str))
        return
    export_run(settings, run, args.output)


def print_runs(store: AuditStore, limit: int) -> None:
    rows = store.list_runs(limit=max(1, min(limit, 200)))
    if not rows:
        print("No audit runs found.")
        return
    print(f"{'RUN ID':36}  {'STATUS':10}  {'IMAGES':6}  {'OBJECTS':7}  {'CREATED'}")
    for run in rows:
        print(
            f"{run.id:36}  {run.status:10}  {run.image_count:6d}  "
            f"{run.total_detections:7d}  {run.created_at.isoformat()}"
        )


def run_payload(run) -> dict:
    image_weights = [image_weight(image) for image in run.images]
    image_ranges = [image_weight_range(image) for image in run.images]
    return {
        "run_id": run.id,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "status": run.status,
        "model_path": run.model_path,
        "device": run.device,
        "confidence_threshold": run.confidence_threshold,
        "image_count": run.image_count,
        "total_detections": run.total_detections,
        "estimated_weight_kg": sum(image_weights) / len(image_weights) if image_weights else 0.0,
        "expected_weight_min_kg": (
            sum(weight_min for weight_min, _ in image_ranges) / len(image_ranges)
            if image_ranges
            else 0.0
        ),
        "expected_weight_max_kg": (
            sum(weight_max for _, weight_max in image_ranges) / len(image_ranges)
            if image_ranges
            else 0.0
        ),
        "weight_aggregation": "mean",
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
        "images": [
            {
                "image_id": image.id,
                "original_filename": image.original_filename,
                "input_path": image.input_path,
                "output_path": image.output_path,
                "sha256": image.sha256,
                "dimensions": [image.width, image.height],
                "detection_count": image.detection_count,
                "mean_confidence": image.mean_confidence,
                "estimated_weight_kg": image_weight(image),
                "expected_weight_min_kg": image_weight_range(image)[0],
                "expected_weight_max_kg": image_weight_range(image)[1],
                "detections": image.detections,
            }
            for image in run.images
        ],
    }


def export_run(settings: Settings, run, requested_output: str | None) -> None:
    export_dir = (
        Path(requested_output).resolve()
        if requested_output
        else (ROOT / "audit_exports" / run.id).resolve()
    )
    assets_dir = export_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    image_sections = []
    image_ranges = []
    for position, image in enumerate(run.images, start=1):
        image_weight_min, image_weight_max = image_weight_range(image)
        image_ranges.append((image_weight_min, image_weight_max))
        input_source = safe_data_path(settings.data_dir, image.input_path)
        output_source = safe_data_path(settings.data_dir, image.output_path)
        input_name = f"{position:02d}_input{input_source.suffix.lower() or '.jpg'}"
        output_name = f"{position:02d}_output{output_source.suffix.lower() or '.jpg'}"
        shutil.copy2(input_source, assets_dir / input_name)
        shutil.copy2(output_source, assets_dir / output_name)

        detection_rows = "".join(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(detection['label'].replace('_', ' ').title())}</td>"
            f"<td>{detection['confidence'] * 100:.1f}%</td>"
            f"<td>{format_weight_range(*detection_weight_range(detection))}</td>"
            f"<td>{html.escape(', '.join(str(round(value)) for value in detection['box_xyxy']))}</td>"
            "</tr>"
            for index, detection in enumerate(image.detections, start=1)
        )
        if not detection_rows:
            detection_rows = '<tr><td colspan="5">No detections above threshold.</td></tr>'

        image_sections.append(
            f"""
            <section>
              <div class="section-title">
                <div><span>Image {position}</span><h2>{html.escape(image.original_filename)}</h2></div>
                <strong>{image.detection_count} detections · {format_weight_range(image_weight_min, image_weight_max)}</strong>
              </div>
              <div class="images">
                <figure><img src="assets/{input_name}" alt="Input image"><figcaption>Input</figcaption></figure>
                <figure><img src="assets/{output_name}" alt="Annotated output"><figcaption>Output</figcaption></figure>
              </div>
              <table>
                <thead><tr><th>#</th><th>Material</th><th>Confidence</th><th>Expected weight range</th><th>Box x1,y1,x2,y2</th></tr></thead>
                <tbody>{detection_rows}</tbody>
              </table>
            </section>
            """
        )

    aggregate_min = (
        sum(weight_min for weight_min, _ in image_ranges) / len(image_ranges)
        if image_ranges
        else 0.0
    )
    aggregate_max = (
        sum(weight_max for _, weight_max in image_ranges) / len(image_ranges)
        if image_ranges
        else 0.0
    )
    report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Audit run {html.escape(run.id)}</title>
  <style>
    *{{box-sizing:border-box}} body{{margin:0;background:#eef2f0;color:#17211e;font:14px/1.5 Arial,sans-serif}}
    header{{padding:24px max(24px,calc((100vw - 1180px)/2));background:#12241f;color:white;border-bottom:3px solid #1f8a70}}
    header span{{color:#aebbb6;font-size:12px}} header h1{{margin:3px 0 0;font-size:24px}}
    main{{max-width:1180px;margin:0 auto;padding:24px}} .summary{{display:grid;grid-template-columns:repeat(5,1fr);background:white;border:1px solid #d6dedb}}
    .summary div{{padding:15px;border-right:1px solid #d6dedb}} .summary div:last-child{{border:0}} .summary span{{display:block;color:#66726e;font-size:11px;text-transform:uppercase}}
    .summary strong{{display:block;margin-top:4px;font-size:18px}} section{{margin-top:20px;background:white;border:1px solid #d6dedb}}
    .section-title{{padding:13px 16px;display:flex;align-items:center;justify-content:space-between;background:#f6f8f7;border-bottom:1px solid #d6dedb}}
    .section-title span{{color:#66726e;font-size:10px;text-transform:uppercase}} .section-title h2{{margin:2px 0 0;font-size:14px}}
    .section-title>strong{{color:#14634f;font-size:12px}} .images{{display:grid;grid-template-columns:1fr 1fr;background:#17211e}}
    figure{{margin:0;display:grid;grid-template-rows:minmax(300px,520px) 34px}} figure:first-child{{border-right:1px solid #4b5d56}}
    figure img{{width:100%;height:100%;object-fit:contain}} figcaption{{padding:8px 12px;color:#c4ceca;background:#0f1a17;font-size:11px}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:9px 12px;text-align:left;border-top:1px solid #e6ebe9}} th{{color:#66726e;background:#f8faf9;font-size:10px;text-transform:uppercase}}
    @media(max-width:720px){{.summary{{grid-template-columns:1fr 1fr}}.summary div:nth-child(2){{border-right:0}}.images{{grid-template-columns:1fr}}figure:first-child{{border-right:0;border-bottom:1px solid #4b5d56}}}}
  </style>
</head>
<body>
  <header><span>Private inference audit</span><h1>AI-Assisted Scrap Detection And Weight Estimation</h1></header>
  <main>
    <div class="summary">
      <div><span>Run ID</span><strong>{html.escape(run.id[:8])}</strong></div>
      <div><span>Status</span><strong>{html.escape(run.status.title())}</strong></div>
      <div><span>Images</span><strong>{run.image_count}</strong></div>
      <div><span>Detections</span><strong>{run.total_detections}</strong></div>
      <div><span>Expected pile range</span><strong>{format_weight_range(aggregate_min, aggregate_max)}</strong></div>
    </div>
    {''.join(image_sections)}
  </main>
</body>
</html>"""
    report_path = export_dir / "audit_report.html"
    report_path.write_text(report, encoding="utf-8")
    (export_dir / "audit_record.json").write_text(
        json.dumps(run_payload(run), indent=2, default=str),
        encoding="utf-8",
    )
    print(f"AUDIT_REPORT={report_path}")
    print(f"AUDIT_JSON={export_dir / 'audit_record.json'}")


def safe_data_path(data_dir: Path, relative_path: str) -> Path:
    root = data_dir.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Invalid audit path: {relative_path}")
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    return candidate


def image_weight(image) -> float:
    return sum(float(item.get("estimated_weight_kg") or 0.0) for item in image.detections)


def detection_weight_range(detection: dict) -> tuple[float, float]:
    midpoint = float(detection.get("estimated_weight_kg") or 0.0)
    return (
        float(detection.get("expected_weight_min_kg", midpoint) or 0.0),
        float(detection.get("expected_weight_max_kg", midpoint) or 0.0),
    )


def image_weight_range(image) -> tuple[float, float]:
    ranges = [detection_weight_range(detection) for detection in image.detections]
    return (
        sum(weight_min for weight_min, _ in ranges),
        sum(weight_max for _, weight_max in ranges),
    )


def format_weight_range(weight_min: float, weight_max: float) -> str:
    if weight_max < 1:
        return f"{round(weight_min * 1000)}-{round(weight_max * 1000)} g"
    return f"{weight_min:.2f}-{weight_max:.2f} kg"


if __name__ == "__main__":
    main()
