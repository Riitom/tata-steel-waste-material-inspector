from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageQualityResult:
    valid: bool
    score: float
    blur_score: float
    contrast_score: float
    brightness: float
    width: int
    height: int
    issues: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class ImageQualityChecker:
    def __init__(
        self,
        minimum_dimension: int = 240,
        minimum_blur_score: float = 20.0,
        minimum_contrast: float = 10.0,
        minimum_brightness: float = 12.0,
        maximum_brightness: float = 245.0,
    ):
        self.minimum_dimension = minimum_dimension
        self.minimum_blur_score = minimum_blur_score
        self.minimum_contrast = minimum_contrast
        self.minimum_brightness = minimum_brightness
        self.maximum_brightness = maximum_brightness

    def assess(self, image: Image.Image) -> ImageQualityResult:
        width, height = image.size
        grayscale = image.convert("L")
        grayscale.thumbnail((640, 640))
        pixels = np.asarray(grayscale, dtype=np.float32)

        brightness = float(pixels.mean())
        contrast = float(pixels.std())
        blur_score = laplacian_variance(pixels)
        issues = []

        if min(width, height) < self.minimum_dimension:
            issues.append(
                f"resolution is too low ({width} x {height}px; minimum side is "
                f"{self.minimum_dimension}px)"
            )
        if blur_score < self.minimum_blur_score:
            issues.append(
                f"image appears blurred (sharpness {blur_score:.1f}; minimum "
                f"{self.minimum_blur_score:.1f})"
            )
        if contrast < self.minimum_contrast:
            issues.append(
                f"image has insufficient contrast ({contrast:.1f}; minimum "
                f"{self.minimum_contrast:.1f})"
            )
        if brightness < self.minimum_brightness:
            issues.append("image is too dark for reliable detection")
        if brightness > self.maximum_brightness:
            issues.append("image is overexposed for reliable detection")

        resolution_score = min(1.0, min(width, height) / 640.0)
        sharpness_score = min(1.0, blur_score / max(self.minimum_blur_score * 4.0, 1.0))
        contrast_score = min(1.0, contrast / max(self.minimum_contrast * 4.0, 1.0))
        exposure_score = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)
        score = round(
            100.0
            * (
                0.20 * resolution_score
                + 0.40 * sharpness_score
                + 0.25 * contrast_score
                + 0.15 * exposure_score
            ),
            1,
        )
        return ImageQualityResult(
            valid=not issues,
            score=score,
            blur_score=round(blur_score, 2),
            contrast_score=round(contrast, 2),
            brightness=round(brightness, 2),
            width=width,
            height=height,
            issues=issues,
        )


def laplacian_variance(pixels: np.ndarray) -> float:
    if pixels.ndim != 2 or min(pixels.shape) < 3:
        return 0.0
    center = pixels[1:-1, 1:-1]
    laplacian = (
        pixels[:-2, 1:-1]
        + pixels[2:, 1:-1]
        + pixels[1:-1, :-2]
        + pixels[1:-1, 2:]
        - 4.0 * center
    )
    return float(laplacian.var())
