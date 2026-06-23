export type HealthResponse = {
  status: string
  model_ready: boolean
  device: string
  model_name: string
  class_count: number
  input_size: number
  model_error: string | null
}

export type Detection = {
  label: string
  class_id: number
  confidence: number
  box_xyxy: number[]
  category: string | null
  area_px_used: number | null
  estimated_weight_kg: number | null
  expected_weight_min_kg: number | null
  expected_weight_max_kg: number | null
  weight_method: string | null
}

export type ImageResult = {
  image_id: number
  filename: string
  width: number
  height: number
  input_url: string
  output_url: string
  detection_count: number
  mean_confidence: number | null
  estimated_weight_kg: number
  expected_weight_min_kg: number
  expected_weight_max_kg: number
  totals_by_material_kg: Record<string, number>
  detections: Detection[]
}

export type PredictionRun = {
  run_id: string
  created_at: string
  confidence_threshold: number
  duration_ms: number
  total_detections: number
  estimated_weight_kg: number
  expected_weight_min_kg: number
  expected_weight_max_kg: number
  weight_aggregation: string
  pixel_area_cm2: number
  images: ImageResult[]
}

export type QueuedImage = {
  id: string
  file: File
  previewUrl: string
}
