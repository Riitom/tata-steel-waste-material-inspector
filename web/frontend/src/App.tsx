import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileImage,
  Gauge,
  Image as ImageIcon,
  LoaderCircle,
  Play,
  RotateCcw,
  Ruler,
  ScanLine,
  Server,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getHealth, runPrediction } from './api'
import type { HealthResponse, ImageResult, PredictionRun, QueuedImage } from './types'
import './App.css'

const MAX_FILES = 12
const DEFAULT_CONFIDENCE = 0.6
const DEFAULT_PIXEL_AREA_CM2 = 0.05

function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [queue, setQueue] = useState<QueuedImage[]>([])
  const [confidence, setConfidence] = useState(DEFAULT_CONFIDENCE)
  const [pixelAreaCm2, setPixelAreaCm2] = useState(DEFAULT_PIXEL_AREA_CM2)
  const [isDragging, setIsDragging] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PredictionRun | null>(null)
  const [activeViews, setActiveViews] = useState<Record<number, 'input' | 'output'>>({})

  useEffect(() => {
    getHealth()
      .then((payload) => {
        setHealth(payload)
        setHealthError(false)
      })
      .catch(() => setHealthError(true))
  }, [])

  useEffect(
    () => () => {
      queue.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    },
    [queue],
  )

  const categoryCounts = useMemo(() => {
    if (!result) return []
    const counts = new Map<string, number>()
    result.images.forEach((image) => {
      image.detections.forEach((detection) => {
        counts.set(detection.label, (counts.get(detection.label) ?? 0) + 1)
      })
    })
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [result])

  const averageConfidence = useMemo(() => {
    if (!result) return null
    const scores = result.images.flatMap((image) =>
      image.detections.map((detection) => detection.confidence),
    )
    if (!scores.length) return null
    return scores.reduce((sum, value) => sum + value, 0) / scores.length
  }, [result])

  function addFiles(fileList: FileList | File[]) {
    const incoming = Array.from(fileList).filter((file) => file.type.startsWith('image/'))
    if (!incoming.length) {
      setError('Choose JPG, PNG, WEBP, BMP, or another valid image format.')
      return
    }

    setQueue((current) => {
      const remaining = MAX_FILES - current.length
      const additions = incoming.slice(0, remaining).map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`,
        file,
        previewUrl: URL.createObjectURL(file),
      }))
      if (incoming.length > remaining) {
        setError(`A maximum of ${MAX_FILES} images can be processed in one run.`)
      } else {
        setError(null)
      }
      return [...current, ...additions]
    })
    setResult(null)
  }

  function removeFile(id: string) {
    setQueue((current) => {
      const item = current.find((candidate) => candidate.id === id)
      if (item) URL.revokeObjectURL(item.previewUrl)
      return current.filter((candidate) => candidate.id !== id)
    })
  }

  function clearWorkspace() {
    queue.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    setQueue([])
    setResult(null)
    setError(null)
    setActiveViews({})
  }

  async function analyze() {
    if (!queue.length || isRunning) return
    setIsRunning(true)
    setError(null)
    setResult(null)
    try {
      const payload = await runPrediction(
        queue.map((item) => item.file),
        confidence,
        50,
        pixelAreaCm2,
      )
      setResult(payload)
      setActiveViews(
        Object.fromEntries(payload.images.map((image) => [image.image_id, 'output'])),
      )
      window.setTimeout(() => {
        document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 50)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The analysis could not be completed.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <ScanLine size={22} />
          </span>
          <div>
            <strong>Waste Material Inspector</strong>
            <span>YOLO visual assessment</span>
          </div>
        </div>
        <ModelStatus health={health} hasError={healthError} />
      </header>

      <main>
        <section className="workspace-band">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Inspection workspace</span>
              <h1>Analyze material images</h1>
              <p>Upload one or more waste-pile images and review the detected material classes.</p>
            </div>
            {(queue.length > 0 || result) && (
              <button className="icon-text-button secondary" type="button" onClick={clearWorkspace}>
                <RotateCcw size={17} />
                Reset
              </button>
            )}
          </div>

          <div className="workspace-grid">
            <div className="upload-workspace">
              <div
                className={`drop-zone ${isDragging ? 'dragging' : ''}`}
                onDragEnter={(event) => {
                  event.preventDefault()
                  setIsDragging(true)
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => {
                  event.preventDefault()
                  if (event.currentTarget === event.target) setIsDragging(false)
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  setIsDragging(false)
                  addFiles(event.dataTransfer.files)
                }}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  hidden
                  onChange={(event) => {
                    if (event.target.files) addFiles(event.target.files)
                    event.target.value = ''
                  }}
                />
                <span className="drop-icon" aria-hidden="true">
                  <Upload size={28} />
                </span>
                <div>
                  <strong>Drop inspection images here</strong>
                  <span>Up to {MAX_FILES} images, 20 MB each</span>
                </div>
                <button
                  className="icon-text-button primary"
                  type="button"
                  onClick={() => inputRef.current?.click()}
                >
                  <FileImage size={17} />
                  Choose images
                </button>
              </div>

              <div className="queue-header">
                <div>
                  <h2>Upload queue</h2>
                  <span>{queue.length} of {MAX_FILES} selected</span>
                </div>
                {queue.length > 0 && (
                  <button
                    className="icon-button"
                    type="button"
                    title="Clear upload queue"
                    aria-label="Clear upload queue"
                    onClick={clearWorkspace}
                  >
                    <Trash2 size={18} />
                  </button>
                )}
              </div>

              {queue.length === 0 ? (
                <div className="empty-queue">
                  <ImageIcon size={24} />
                  <span>Selected images will appear here.</span>
                </div>
              ) : (
                <div className="file-grid">
                  {queue.map((item) => (
                    <article className="file-card" key={item.id}>
                      <img src={item.previewUrl} alt="" />
                      <div className="file-meta">
                        <strong title={item.file.name}>{item.file.name}</strong>
                        <span>{formatBytes(item.file.size)}</span>
                      </div>
                      <button
                        className="remove-button"
                        type="button"
                        aria-label={`Remove ${item.file.name}`}
                        title="Remove image"
                        onClick={() => removeFile(item.id)}
                      >
                        <X size={16} />
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <aside className="control-panel" aria-label="Analysis settings">
              <div className="control-heading">
                <Gauge size={20} />
                <div>
                  <h2>Detection settings</h2>
                </div>
              </div>

              <label className="slider-label" htmlFor="confidence">
                <span>
                  Confidence threshold
                </span>
                <output>{Math.round(confidence * 100)}%</output>
              </label>
              <input
                id="confidence"
                className="confidence-slider"
                type="range"
                min="0.3"
                max="0.9"
                step="0.05"
                value={confidence}
                onChange={(event) => setConfidence(Number(event.target.value))}
              />
              <div className="range-labels" aria-hidden="true">
                <span>More detections</span>
                <span>More precise</span>
              </div>

              <label className="calibration-control" htmlFor="pixel-area">
                <span>
                  <Ruler size={17} />
                  Image scale
                </span>
                <div>
                  <input
                    id="pixel-area"
                    type="number"
                    min="0.000001"
                    max="100"
                    step="0.001"
                    value={pixelAreaCm2}
                    onChange={(event) => setPixelAreaCm2(Number(event.target.value))}
                  />
                  <span>cm²/px</span>
                </div>
              </label>

              <div className="model-facts">
                <Fact icon={<Server size={17} />} label="Processor" value={health?.device ?? 'Checking'} />
                <Fact icon={<ScanLine size={17} />} label="Classes" value={health ? String(health.class_count) : '—'} />
                <Fact icon={<ImageIcon size={17} />} label="Input size" value={health ? `${health.input_size} px` : '640 px'} />
              </div>

              <button
                className="analyze-button"
                type="button"
                disabled={
                  !queue.length ||
                  isRunning ||
                  healthError ||
                  health?.model_ready === false ||
                  pixelAreaCm2 <= 0
                }
                onClick={analyze}
              >
                {isRunning ? <LoaderCircle className="spin" size={19} /> : <Play size={19} />}
                {isRunning ? `Analyzing ${queue.length} image${queue.length === 1 ? '' : 's'}` : 'Run detection'}
              </button>

            </aside>
          </div>

          {error && (
            <div className="error-banner" role="alert">
              <AlertCircle size={19} />
              <span>{error}</span>
            </div>
          )}
        </section>

        {result && (
          <section className="results-band" id="results">
            <div className="section-heading compact">
              <div>
                <span className="eyebrow">Run complete</span>
                <h2>Inspection results</h2>
                <p>Run ID {result.run_id.slice(0, 8)} · {formatDuration(result.duration_ms)}</p>
              </div>
              <span className="success-mark">
                <CheckCircle2 size={18} />
                Processed
              </span>
            </div>

            <div className="metric-row">
              <Metric label="Images" value={String(result.images.length)} />
              <Metric label="Detections" value={String(result.total_detections)} />
              <Metric
                label="Expected pile range"
                value={formatWeightRange(
                  result.expected_weight_min_kg,
                  result.expected_weight_max_kg,
                )}
              />
              <Metric
                label="Average confidence"
                value={averageConfidence === null ? '—' : `${Math.round(averageConfidence * 100)}%`}
              />
              <Metric label="Threshold" value={`${Math.round(result.confidence_threshold * 100)}%`} />
            </div>

            {categoryCounts.length > 0 && (
              <div className="distribution">
                <h3>Detected material distribution</h3>
                <div className="distribution-list">
                  {categoryCounts.map(([label, count]) => (
                    <div className="distribution-item" key={label}>
                      <span>{displayLabel(label)}</span>
                      <div className="distribution-track" aria-hidden="true">
                        <span
                          style={{
                            width: `${Math.max(8, (count / categoryCounts[0][1]) * 100)}%`,
                          }}
                        />
                      </div>
                      <strong>{count}</strong>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="result-list">
              {result.images.map((image, index) => (
                <ResultItem
                  key={image.image_id}
                  image={image}
                  index={index}
                  activeView={activeViews[image.image_id] ?? 'output'}
                  onViewChange={(view) =>
                    setActiveViews((current) => ({ ...current, [image.image_id]: view }))
                  }
                />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

function ModelStatus({ health, hasError }: { health: HealthResponse | null; hasError: boolean }) {
  const ready = health?.model_ready && !hasError
  return (
    <div className={`model-status ${hasError ? 'error' : ready ? 'ready' : ''}`}>
      <span className="status-dot" />
      <div>
        <strong>{hasError ? 'Service unavailable' : 'Tata Steel'}</strong>
        <span>{health?.model_name ?? 'Connecting to detector'}</span>
      </div>
    </div>
  )
}

function Fact({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="fact">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ResultItem({
  image,
  index,
  activeView,
  onViewChange,
}: {
  image: ImageResult
  index: number
  activeView: 'input' | 'output'
  onViewChange: (view: 'input' | 'output') => void
}) {
  return (
    <article className="result-item">
      <div className="result-toolbar">
        <div>
          <span>Image {index + 1}</span>
          <strong>{image.filename}</strong>
        </div>
        <div className="result-actions">
          <div className="segmented-control" aria-label="Image view">
            <button
              type="button"
              className={activeView === 'input' ? 'active' : ''}
              onClick={() => onViewChange('input')}
            >
              <ImageIcon size={16} />
              Input
            </button>
            <button
              type="button"
              className={activeView === 'output' ? 'active' : ''}
              onClick={() => onViewChange('output')}
            >
              <ScanLine size={16} />
              Detection
            </button>
          </div>
          <a
            className="icon-button"
            href={image.output_url}
            download={`${image.filename.replace(/\.[^.]+$/, '')}_detected.jpg`}
            title="Download annotated image"
            aria-label="Download annotated image"
          >
            <Download size={18} />
          </a>
        </div>
      </div>

      <div className="result-body">
        <figure className="image-viewer">
          <img
            src={activeView === 'input' ? image.input_url : image.output_url}
            alt={activeView === 'input' ? `Uploaded ${image.filename}` : `Detected materials in ${image.filename}`}
          />
          <figcaption>
            {image.width} × {image.height}px
            <span>{activeView === 'input' ? 'Original input' : 'Annotated output'}</span>
          </figcaption>
        </figure>

        <div className="detection-panel">
          <div className="detection-summary">
            <div>
              <span>Objects found</span>
              <strong>{image.detection_count}</strong>
            </div>
            <div>
              <span>Mean confidence</span>
              <strong>{image.mean_confidence === null ? '—' : `${Math.round(image.mean_confidence * 100)}%`}</strong>
            </div>
            <div>
              <span>Expected weight</span>
              <strong>
                {formatWeightRange(
                  image.expected_weight_min_kg,
                  image.expected_weight_max_kg,
                )}
              </strong>
            </div>
          </div>

          {image.detections.length === 0 ? (
            <div className="no-detections">
              <AlertCircle size={20} />
              <span>No object passed the selected confidence threshold.</span>
            </div>
          ) : (
            <div className="detection-list">
              {image.detections.map((detection, detectionIndex) => (
                <div className="detection-row" key={`${detection.label}-${detectionIndex}`}>
                  <span className="detection-index">{detectionIndex + 1}</span>
                  <div>
                    <strong>{displayLabel(detection.label)}</strong>
                    <span>{detection.box_xyxy.map((value) => Math.round(value)).join(', ')}</span>
                  </div>
                  <div className="detection-values">
                    <b>{Math.round(detection.confidence * 100)}%</b>
                    <span>
                      {formatWeightRange(
                        detection.expected_weight_min_kg ?? 0,
                        detection.expected_weight_max_kg ?? 0,
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

function displayLabel(label: string) {
  return label.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDuration(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds} ms`
  return `${(milliseconds / 1000).toFixed(1)} s`
}

function formatWeightRange(weightMinKg: number, weightMaxKg: number) {
  if (weightMaxKg < 1) {
    return `${Math.round(weightMinKg * 1000)}–${Math.round(weightMaxKg * 1000)} g`
  }
  return `${weightMinKg.toFixed(2)}–${weightMaxKg.toFixed(2)} kg`
}

export default App
