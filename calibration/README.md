# Weight Calibration Measurements

Create one row for one weighed object or one single-material pile.

Required values:

- `sample_id`: unique sample name
- `material`: exact class name from `configs/materials.yaml`
- `split`: use `calibrate` for fitting and `validate` for held-out evaluation
- `box_area_px`: bounding-box area in pixels; sum multiple boxes when the
  measured weight covers several objects
- `mask_area_px`: optional segmentation-mask area; leave blank when using boxes
- `pixel_area_cm2`: physical square centimetres represented by one pixel
- `measured_weight_kg`: actual weight from a scale
- `notes`: optional setup description

Use a fixed camera height and angle or include a reference marker in every
image. The pixel scale changes when camera distance changes.

Calculate the box area from the detector coordinates:

```text
box_area_px = (x2 - x1) * (y2 - y1)
```

For a flat reference marker:

```text
pixel_area_cm2 = real_marker_area_cm2 / marker_area_px
```

Keep the marker close to the same depth as the material. A marker lying on the
floor will not provide a correct scale for an object significantly above it.

Do not enter several camera views of the same weighed pile as separate
independent samples. Use one representative view per measurement during
calibration, and reserve different piles or objects for validation.

Collect at least 20 varied samples per material where possible. A good initial
split is 70% `calibrate` and 30% `validate`. Five calibration samples is the
minimum accepted by the utility, but it is not enough for a strong operational
estimate.

Run:

```powershell
python scripts\calibrate_materials.py
```

This creates `configs/materials.calibrated.yaml`. Review its metrics, then use
it temporarily:

```powershell
$env:WASTE_MATERIALS_PATH="configs/materials.calibrated.yaml"
.\start_app.ps1
```

After validating the result on held-out weighed samples, replace the production
configuration:

```powershell
python scripts\calibrate_materials.py --in-place
```

The in-place mode creates `configs/materials.yaml.bak` first.
