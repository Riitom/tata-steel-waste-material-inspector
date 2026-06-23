from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


REFINED_MATERIALS = {"plastics", "wood"}


def estimate_foreground_area(
    image: Image.Image,
    box_xyxy: list[float] | tuple[float, float, float, float],
    label: str,
    fallback_fill_ratio: float,
) -> tuple[float | None, float | None, str | None]:
    if label not in REFINED_MATERIALS:
        return None, None, None

    x1, y1, x2, y2 = box_xyxy
    left = max(0, min(image.width - 1, round(x1)))
    top = max(0, min(image.height - 1, round(y1)))
    right = max(left + 1, min(image.width, round(x2)))
    bottom = max(top + 1, min(image.height, round(y2)))
    box_area = float((right - left) * (bottom - top))
    if box_area < 400:
        return None, None, None

    crop = image.crop((left, top, right, bottom)).convert("RGB")
    original_size = crop.size
    crop.thumbnail((256, 256))
    pixels = np.asarray(crop, dtype=np.float32)
    if min(pixels.shape[:2]) < 8:
        return None, None, None

    border = np.concatenate(
        (
            pixels[0, :, :],
            pixels[-1, :, :],
            pixels[:, 0, :],
            pixels[:, -1, :],
        ),
        axis=0,
    )
    background = np.median(border, axis=0)
    border_spread = float(np.median(np.linalg.norm(border - background, axis=1)))
    distance = np.linalg.norm(pixels - background, axis=2)
    threshold = max(
        22.0,
        float(np.percentile(np.linalg.norm(border - background, axis=1), 70)) * 1.25,
    )
    mask = Image.fromarray(np.uint8(distance > threshold) * 255, mode="L")
    mask = mask.filter(ImageFilter.MedianFilter(size=3))
    foreground_fraction = float(np.asarray(mask, dtype=np.float32).mean() / 255.0)

    lower = max(0.12, fallback_fill_ratio * 0.45)
    upper = min(0.92, fallback_fill_ratio * 1.45)
    if border_spread <= 35.0 and lower <= foreground_fraction <= upper:
        reliability = max(0.45, min(1.0, 1.0 - border_spread / 52.0))
        scale = (original_size[0] * original_size[1]) / float(crop.width * crop.height)
        foreground_area = foreground_fraction * crop.width * crop.height * scale
        return foreground_area, reliability, "foreground_refined_area"

    box_width = right - left
    box_height = bottom - top
    aspect_ratio = max(box_width / box_height, box_height / box_width)
    image_coverage = box_area / float(image.width * image.height)
    touches_edge = (
        left <= 2
        or top <= 2
        or right >= image.width - 2
        or bottom >= image.height - 2
    )

    if label == "plastics":
        if image_coverage >= 0.55:
            fill_ratio = 0.22
        elif image_coverage >= 0.25:
            fill_ratio = 0.32
        else:
            fill_ratio = min(fallback_fill_ratio, 0.45)
        if touches_edge:
            fill_ratio *= 0.90
    else:
        fill_ratio = 0.78 if aspect_ratio >= 2.2 else 0.62
        if image_coverage >= 0.40:
            fill_ratio = min(fill_ratio, 0.55)
        if touches_edge:
            fill_ratio *= 0.88

    return box_area * fill_ratio, 0.50, "geometry_refined_area"
