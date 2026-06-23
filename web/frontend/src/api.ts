import type { HealthResponse, PredictionRun } from './types'

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) message = payload.detail
    } catch {
      // Keep the HTTP fallback when the response is not JSON.
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health')
}

export function runPrediction(
  files: File[],
  confidence: number,
  maxDetections: number,
  pixelAreaCm2: number,
): Promise<PredictionRun> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('confidence', confidence.toString())
  form.append('max_detections', maxDetections.toString())
  form.append('pixel_area_cm2', pixelAreaCm2.toString())
  return requestJson<PredictionRun>('/api/predict', {
    method: 'POST',
    body: form,
  })
}
