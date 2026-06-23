from __future__ import annotations

from pathlib import Path

import yaml

from waste_detector.types import MaterialProfile


def load_material_profiles(path: str | Path) -> dict[str, MaterialProfile]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    materials = raw.get("materials", [])
    if not materials:
        raise ValueError(f"No materials found in {config_path}")

    profiles: dict[str, MaterialProfile] = {}
    for item in materials:
        profile = MaterialProfile(
            name=str(item["name"]),
            category=str(item.get("category", item["name"])),
            density_kg_m3=float(item["density_kg_m3"]),
            default_thickness_cm=float(item["default_thickness_cm"]),
            box_fill_ratio=float(item.get("box_fill_ratio", 0.6)),
            weight_uncertainty_ratio=float(item.get("weight_uncertainty_ratio", 0.35)),
        )
        if not 0 <= profile.weight_uncertainty_ratio < 1:
            raise ValueError(
                f"weight_uncertainty_ratio for {profile.name} must be between 0 and 1"
            )
        profiles[profile.name] = profile

    return profiles
