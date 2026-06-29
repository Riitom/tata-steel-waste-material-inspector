import type {
  ApiProblem,
  DashboardSummary,
  HealthResponse,
  HistoryRun,
  HistoryRunDetail,
  PredictionRun,
} from './types'

export class ApiError extends Error {
  problem: ApiProblem

  constructor(problem: ApiProblem) {
    super(problem.message)
    this.problem = problem
  }
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    let problem: ApiProblem = { message: `Request failed (${response.status})` }
    try {
      const payload = (await response.json()) as { detail?: string | ApiProblem }
      if (typeof payload.detail === 'string') {
        problem = { message: payload.detail }
      } else if (payload.detail) {
        problem = payload.detail
      }
    } catch {
      // Keep the HTTP fallback for non-JSON responses.
    }
    throw new ApiError(problem)
  }
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>('/api/health')
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return requestJson<DashboardSummary>('/api/dashboard/summary')
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

export function getHistoryRuns(limit = 100): Promise<HistoryRun[]> {
  return requestJson<HistoryRun[]>(`/api/history/runs?limit=${limit}`)
}

export function getHistoryRun(runId: string): Promise<HistoryRunDetail> {
  return requestJson<HistoryRunDetail>(`/api/history/runs/${runId}`)
}

export function rerunHistory(
  runId: string,
  confidence: number,
  maxDetections: number,
  pixelAreaCm2: number,
): Promise<PredictionRun> {
  const form = new FormData()
  form.append('confidence', confidence.toString())
  form.append('max_detections', maxDetections.toString())
  form.append('pixel_area_cm2', pixelAreaCm2.toString())
  return requestJson<PredictionRun>(`/api/history/runs/${runId}/rerun`, {
    method: 'POST',
    body: form,
  })
}
