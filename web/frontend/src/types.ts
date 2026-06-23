export type HealthResponse = {
  status: string
  model_ready: boolean
  device: string
  model_name: string
  class_count: number
  input_size: number
  model_error: string | null
}

export type DashboardDailyActivity = {
  date: string
  label: string
  runs: number
  images: number
  detections: number
}

export type DashboardMaterialCount = {
  label: string
  count: number
}

export type DashboardSummary = {
  generated_at: string
  timezone: string
  today_label: string
  total_runs: number
  today_runs: number
  completed_runs: number
  failed_runs: number
  total_images: number
  today_images: number
  total_detections: number
  today_detections: number
  success_rate: number
  average_duration_ms: number | null
  daily_activity: DashboardDailyActivity[]
  material_counts: DashboardMaterialCount[]
}

export type ImageQuality = {
  valid: boolean
  score: number
  blur_score: number
  contrast_score: number
  brightness: number
  width: number
  height: number
  issues: string[]
}

export type Detection = {
  label: string
  class_id: number
  confidence: number
  box_xyxy: number[]
  category: string | null
  area_px_used: number | null
  area_refinement_reliability: number | null
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
  input_url: string | null
  output_url: string | null
  detection_count: number
  mean_confidence: number | null
  estimated_weight_kg: number
  expected_weight_min_kg: number
  expected_weight_max_kg: number
  totals_by_material_kg: Record<string, number>
  quality: ImageQuality | null
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
  source_run_id: string | null
  images: ImageResult[]
}

export type HistoryRun = {
  run_id: string
  created_at: string
  completed_at: string | null
  status: string
  image_count: number
  total_detections: number
  confidence_threshold: number
  duration_ms: number | null
  source_run_id: string | null
  pixel_area_cm2: number | null
  preview_input_url: string | null
  preview_output_url: string | null
  preview_filename: string | null
  mean_confidence: number | null
  expected_weight_min_kg: number
  expected_weight_max_kg: number
}

export type HistoryRunDetail = {
  run_id: string
  created_at: string
  completed_at: string | null
  status: string
  image_count: number
  total_detections: number
  confidence_threshold: number
  duration_ms: number | null
  model_path: string
  device: string
  error_message: string | null
  source_run_id: string | null
  pixel_area_cm2: number | null
  expected_weight_min_kg: number
  expected_weight_max_kg: number
  images: ImageResult[]
}

export type QueuedImage = {
  id: string
  file: File
  previewUrl: string
}

export type QualityFailure = {
  filename: string
  score: number
  issues: string[]
}

export type ApiProblem = {
  code?: string
  message: string
  images?: QualityFailure[]
}
