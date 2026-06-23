from __future__ import annotations

import argparse
import csv
import math
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waste_detector.config import load_material_profiles


REQUIRED_COLUMNS = {
    "sample_id",
    "material",
    "box_area_px",
    "mask_area_px",
    "pixel_area_cm2",
    "measured_weight_kg",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit per-material weight correction factors from measured samples."
    )
    parser.add_argument(
        "--measurements",
        default="calibration/material_measurements.csv",
        help="CSV containing image-area measurements and actual scale weights.",
    )
    parser.add_argument(
        "--materials",
        default="configs/materials.yaml",
        help="Existing material profile YAML.",
    )
    parser.add_argument(
        "--output",
        default="configs/materials.calibrated.yaml",
        help="Output YAML. The source file is not overwritten by default.",
    )
    parser.add_argument("--minimum-samples", type=int, default=5)
    parser.add_argument(
        "--coverage",
        type=float,
        default=0.90,
        help="Fraction of calibration relative errors covered by the displayed range.",
    )
    parser.add_argument("--minimum-uncertainty", type=float, default=0.10)
    parser.add_argument("--maximum-uncertainty", type=float, default=0.95)
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Replace the source YAML after creating a .bak backup.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.minimum_samples < 2:
        raise SystemExit("--minimum-samples must be at least 2")
    if not 0 < args.coverage <= 1:
        raise SystemExit("--coverage must be between 0 and 1")
    if not 0 <= args.minimum_uncertainty <= args.maximum_uncertainty < 1:
        raise SystemExit("Uncertainty bounds must satisfy 0 <= minimum <= maximum < 1")

    measurements_path = resolve_path(args.measurements)
    materials_path = resolve_path(args.materials)
    output_path = materials_path if args.in_place else resolve_path(args.output)

    profiles = load_material_profiles(materials_path)
    raw_config = yaml.safe_load(materials_path.read_text(encoding="utf-8")) or {}
    rows = read_measurements(measurements_path, profiles)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["material"]].append(row)

    fitted = {}
    for material, all_samples in sorted(grouped.items()):
        calibration_samples = [
            sample for sample in all_samples if sample["split"] == "calibrate"
        ]
        validation_samples = [
            sample for sample in all_samples if sample["split"] == "validate"
        ]
        if len(calibration_samples) < args.minimum_samples:
            print(
                f"SKIP material={material} samples={len(calibration_samples)} "
                f"required={args.minimum_samples}",
                flush=True,
            )
            continue
        profile = profiles[material]
        baseline_predictions = [
            baseline_weight_kg(sample, profile)
            for sample in calibration_samples
        ]
        ratios = [
            sample["measured_weight_kg"] / prediction
            for sample, prediction in zip(calibration_samples, baseline_predictions)
            if prediction > 0
        ]
        calibration_factor = median(ratios)
        evaluation_samples = validation_samples or calibration_samples
        evaluation_source = "validation" if validation_samples else "calibration"
        evaluation_baseline = [
            baseline_weight_kg(sample, profile)
            for sample in evaluation_samples
        ]
        evaluation_calibrated = [
            prediction * calibration_factor
            for prediction in evaluation_baseline
        ]
        relative_errors = [
            abs(prediction - sample["measured_weight_kg"])
            / sample["measured_weight_kg"]
            for sample, prediction in zip(evaluation_samples, evaluation_calibrated)
        ]
        uncertainty = min(
            args.maximum_uncertainty,
            max(args.minimum_uncertainty, quantile(relative_errors, args.coverage)),
        )
        fitted[material] = {
            "calibration_factor": calibration_factor,
            "weight_uncertainty_ratio": uncertainty,
            "calibration_samples": len(calibration_samples),
            "validation_samples": len(validation_samples),
            "evaluation_source": evaluation_source,
            "baseline_mae_kg": mae(
                [sample["measured_weight_kg"] for sample in evaluation_samples],
                evaluation_baseline,
            ),
            "calibrated_mae_kg": mae(
                [sample["measured_weight_kg"] for sample in evaluation_samples],
                evaluation_calibrated,
            ),
            "baseline_mape": mape(
                [sample["measured_weight_kg"] for sample in evaluation_samples],
                evaluation_baseline,
            ),
            "calibrated_mape": mape(
                [sample["measured_weight_kg"] for sample in evaluation_samples],
                evaluation_calibrated,
            ),
        }

    if not fitted:
        raise SystemExit(
            "No material had enough valid samples. Add measurements or lower --minimum-samples."
        )

    for item in raw_config.get("materials", []):
        result = fitted.get(str(item.get("name")))
        if result is None:
            continue
        item["calibration_factor"] = round(result["calibration_factor"], 6)
        item["weight_uncertainty_ratio"] = round(
            result["weight_uncertainty_ratio"],
            6,
        )

    raw_config["calibration"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "measurements": str(measurements_path),
        "coverage": args.coverage,
        "minimum_samples": args.minimum_samples,
        "results": {
            material: {
                key: round(value, 6) if isinstance(value, float) else value
                for key, value in result.items()
            }
            for material, result in fitted.items()
        },
    }

    if args.in_place:
        backup_path = materials_path.with_suffix(materials_path.suffix + ".bak")
        shutil.copy2(materials_path, backup_path)
        print(f"BACKUP={backup_path}", flush=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# Generated from measured calibration samples.\n"
        + yaml.safe_dump(raw_config, sort_keys=False),
        encoding="utf-8",
    )

    print_report(fitted)
    print(f"CALIBRATED_MATERIALS={output_path}", flush=True)
    print("MATERIAL_CALIBRATION_PASS", flush=True)


def read_measurements(path: Path, profiles: dict) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")

        rows = []
        for line_number, raw in enumerate(reader, start=2):
            material = str(raw["material"]).strip()
            if not material:
                continue
            if material not in profiles:
                raise ValueError(
                    f"Unknown material '{material}' on CSV line {line_number}"
                )
            measured_weight = positive_float(
                raw["measured_weight_kg"],
                "measured_weight_kg",
                line_number,
            )
            pixel_area = positive_float(
                raw["pixel_area_cm2"],
                "pixel_area_cm2",
                line_number,
            )
            box_area = optional_positive_float(
                raw.get("box_area_px", ""),
                "box_area_px",
                line_number,
            )
            mask_area = optional_positive_float(
                raw.get("mask_area_px", ""),
                "mask_area_px",
                line_number,
            )
            if box_area is None and mask_area is None:
                raise ValueError(
                    f"CSV line {line_number} requires box_area_px or mask_area_px"
                )
            rows.append(
                {
                    "sample_id": str(raw["sample_id"]).strip() or str(line_number),
                    "material": material,
                    "split": normalize_split(raw.get("split", ""), line_number),
                    "box_area_px": box_area,
                    "mask_area_px": mask_area,
                    "pixel_area_cm2": pixel_area,
                    "measured_weight_kg": measured_weight,
                }
            )
    return rows


def normalize_split(value: str, line_number: int) -> str:
    split = str(value).strip().lower()
    if split in {"", "calibrate", "calibration", "train", "fit"}:
        return "calibrate"
    if split in {"validate", "validation", "val", "test"}:
        return "validate"
    raise ValueError(
        f"Invalid split on CSV line {line_number}: use calibrate or validate"
    )


def baseline_weight_kg(sample: dict, profile) -> float:
    if sample["mask_area_px"] is not None:
        area_px = sample["mask_area_px"]
    else:
        area_px = sample["box_area_px"] * profile.box_fill_ratio
    area_cm2 = area_px * sample["pixel_area_cm2"]
    volume_cm3 = area_cm2 * profile.default_thickness_cm
    density_g_cm3 = profile.density_kg_m3 / 1000.0
    return (volume_cm3 * density_g_cm3) / 1000.0


def positive_float(value: str, column: str, line_number: int) -> float:
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid {column} on CSV line {line_number}: {value!r}"
        ) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(
            f"{column} must be greater than zero on CSV line {line_number}"
        )
    return number


def optional_positive_float(
    value: str,
    column: str,
    line_number: int,
) -> float | None:
    if not str(value).strip():
        return None
    return positive_float(value, column, line_number)


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def mae(actual: list[float], predicted: list[float]) -> float:
    return mean(abs(expected - observed) for expected, observed in zip(actual, predicted))


def mape(actual: list[float], predicted: list[float]) -> float:
    return mean(
        abs(expected - observed) / expected
        for expected, observed in zip(actual, predicted)
    )


def print_report(fitted: dict[str, dict]) -> None:
    header = (
        f"{'MATERIAL':20} {'FIT':>5} {'VAL':>5} {'FACTOR':>10} {'RANGE':>10} "
        f"{'MAE BEFORE':>12} {'MAE AFTER':>11} {'MAPE AFTER':>12}"
    )
    print(header)
    for material, result in sorted(fitted.items()):
        print(
            f"{material:20} {result['calibration_samples']:5d} "
            f"{result['validation_samples']:5d} "
            f"{result['calibration_factor']:10.4f} "
            f"{result['weight_uncertainty_ratio']:10.1%} "
            f"{result['baseline_mae_kg']:12.4f} "
            f"{result['calibrated_mae_kg']:11.4f} "
            f"{result['calibrated_mape']:12.1%}"
        )


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


if __name__ == "__main__":
    main()
