from __future__ import annotations

from collections import defaultdict
from statistics import mean

from waste_detector.types import Detection, ImageResult, MaterialProfile, PileSummary


class WeightEstimator:
    """Baseline calibrated weight estimator.

    The estimate is intentionally simple and explainable. Once real image plus
    measured-weight data is available, this can be replaced or corrected with a
    learned regression model.
    """

    def __init__(self, profiles: dict[str, MaterialProfile], pixel_area_cm2: float):
        if pixel_area_cm2 <= 0:
            raise ValueError("pixel_area_cm2 must be greater than zero")
        self.profiles = profiles
        self.pixel_area_cm2 = pixel_area_cm2

    def estimate_detection(self, detection: Detection) -> Detection:
        profile = self.profiles.get(detection.label)
        if profile is None:
            detection.category = "unknown"
            detection.area_px_used = 0.0
            detection.estimated_weight_kg = 0.0
            detection.expected_weight_min_kg = 0.0
            detection.expected_weight_max_kg = 0.0
            detection.weight_method = "skipped_unknown_material"
            return detection

        if detection.mask_area_px is not None and detection.mask_area_px > 0:
            area_px = detection.mask_area_px
            method = "segmentation_mask_area"
        else:
            area_px = detection.box_area_px * profile.box_fill_ratio
            method = "box_area_with_fill_ratio"

        area_cm2 = area_px * self.pixel_area_cm2
        volume_cm3 = area_cm2 * profile.default_thickness_cm
        density_g_cm3 = profile.density_kg_m3 / 1000.0
        baseline_weight_kg = (volume_cm3 * density_g_cm3) / 1000.0
        weight_kg = baseline_weight_kg * profile.calibration_factor

        detection.category = profile.category
        detection.area_px_used = area_px
        detection.estimated_weight_kg = weight_kg
        detection.expected_weight_min_kg = max(
            0.0,
            weight_kg * (1.0 - profile.weight_uncertainty_ratio),
        )
        detection.expected_weight_max_kg = weight_kg * (
            1.0 + profile.weight_uncertainty_ratio
        )
        detection.weight_method = (
            f"{method}_calibrated"
            if profile.calibration_factor != 1.0
            else method
        )
        return detection

    def estimate_image(self, image_path: str, detections: list[Detection], annotated_path: str | None) -> ImageResult:
        estimated = [self.estimate_detection(detection) for detection in detections]

        totals_by_material: dict[str, float] = defaultdict(float)
        totals_by_category: dict[str, float] = defaultdict(float)
        expected_min = 0.0
        expected_max = 0.0

        for detection in estimated:
            weight = detection.estimated_weight_kg or 0.0
            totals_by_material[detection.label] += weight
            totals_by_category[detection.category or "unknown"] += weight
            expected_min += detection.expected_weight_min_kg or 0.0
            expected_max += detection.expected_weight_max_kg or 0.0

        total = sum(totals_by_material.values())

        return ImageResult(
            image_path=image_path,
            annotated_path=annotated_path,
            detections=estimated,
            total_weight_kg=total,
            expected_weight_min_kg=expected_min,
            expected_weight_max_kg=expected_max,
            totals_by_material_kg=dict(totals_by_material),
            totals_by_category_kg=dict(totals_by_category),
        )

    def aggregate_pile(self, image_results: list[ImageResult], aggregation: str = "mean") -> PileSummary:
        if aggregation not in {"mean", "sum", "max"}:
            raise ValueError("aggregation must be one of: mean, sum, max")

        if not image_results:
            return PileSummary(
                aggregation=aggregation,
                image_count=0,
                aggregate_total_weight_kg=0.0,
                expected_weight_min_kg=0.0,
                expected_weight_max_kg=0.0,
                aggregate_by_material_kg={},
                aggregate_by_category_kg={},
                images=[],
            )

        material_keys = sorted({key for result in image_results for key in result.totals_by_material_kg})
        category_keys = sorted({key for result in image_results for key in result.totals_by_category_kg})

        by_material = {
            key: self._aggregate_values(
                [result.totals_by_material_kg.get(key, 0.0) for result in image_results],
                aggregation,
            )
            for key in material_keys
        }
        by_category = {
            key: self._aggregate_values(
                [result.totals_by_category_kg.get(key, 0.0) for result in image_results],
                aggregation,
            )
            for key in category_keys
        }
        total = self._aggregate_values([result.total_weight_kg for result in image_results], aggregation)
        expected_min = self._aggregate_values(
            [result.expected_weight_min_kg for result in image_results],
            aggregation,
        )
        expected_max = self._aggregate_values(
            [result.expected_weight_max_kg for result in image_results],
            aggregation,
        )

        return PileSummary(
            aggregation=aggregation,
            image_count=len(image_results),
            aggregate_total_weight_kg=total,
            expected_weight_min_kg=expected_min,
            expected_weight_max_kg=expected_max,
            aggregate_by_material_kg=by_material,
            aggregate_by_category_kg=by_category,
            images=image_results,
        )

    @staticmethod
    def _aggregate_values(values: list[float], aggregation: str) -> float:
        if aggregation == "sum":
            return sum(values)
        if aggregation == "max":
            return max(values)
        return mean(values)
