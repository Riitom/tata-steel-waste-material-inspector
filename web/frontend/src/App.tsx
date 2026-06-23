import {
  Activity,
  AlertCircle,
  BadgeCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  Database,
  Download,
  FileImage,
  Gauge,
  History,
  Home,
  Image as ImageIcon,
  LoaderCircle,
  Menu,
  Play,
  RefreshCw,
  RotateCcw,
  Ruler,
  ScanLine,
  Search,
  Server,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  getDashboardSummary,
  getHealth,
  getHistoryRun,
  getHistoryRuns,
  rerunHistory,
  runPrediction,
} from './api'
import type {
  ApiProblem,
  DashboardSummary,
  HealthResponse,
  HistoryRun,
  HistoryRunDetail,
  ImageResult,
  PredictionRun,
  QueuedImage,
} from './types'
import './App.css'

const MAX_FILES = 12
const DEFAULT_CONFIDENCE = 0.6
const DEFAULT_PIXEL_AREA_CM2 = 0.05

type ViewName = 'inspect' | 'history' | 'system'

function App() {
  const queueRef = useRef<QueuedImage[]>([])
  const [view, setView] = useState<ViewName>('inspect')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem('material-inspector-sidebar') === 'collapsed',
  )
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(true)
  const [dashboardError, setDashboardError] = useState(false)
  const [queue, setQueue] = useState<QueuedImage[]>([])
  const [confidence, setConfidence] = useState(DEFAULT_CONFIDENCE)
  const [pixelAreaCm2, setPixelAreaCm2] = useState(DEFAULT_PIXEL_AREA_CM2)
  const [isDragging, setIsDragging] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [problem, setProblem] = useState<ApiProblem | null>(null)
  const [result, setResult] = useState<PredictionRun | null>(null)
  const [activeViews, setActiveViews] = useState<Record<number, 'input' | 'output'>>({})
  const [historyRuns, setHistoryRuns] = useState<HistoryRun[]>([])
  const [historyDetail, setHistoryDetail] = useState<HistoryRunDetail | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [historySearch, setHistorySearch] = useState('')

  useEffect(() => {
    getHealth()
      .then((payload) => {
        setHealth(payload)
        setHealthError(false)
      })
      .catch(() => setHealthError(true))
    getDashboardSummary()
      .then((payload) => {
        setDashboard(payload)
        setDashboardError(false)
      })
      .catch(() => setDashboardError(true))
      .finally(() => setDashboardLoading(false))
  }, [])

  useEffect(() => {
    queueRef.current = queue
  }, [queue])

  useEffect(
    () => () => {
      queueRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl))
    },
    [],
  )

  const categoryCounts = useMemo(() => materialCounts(result?.images ?? []), [result])
  const averageConfidence = useMemo(
    () => calculateAverageConfidence(result?.images ?? []),
    [result],
  )
  const filteredHistory = useMemo(() => {
    const term = historySearch.trim().toLowerCase()
    if (!term) return historyRuns
    return historyRuns.filter((run) =>
      [
        run.run_id,
        run.preview_filename ?? '',
        run.status,
        new Date(run.created_at).toLocaleString(),
      ].some((value) => value.toLowerCase().includes(term)),
    )
  }, [historyRuns, historySearch])

  function selectView(nextView: ViewName) {
    setView(nextView)
    setMobileNavOpen(false)
    if (nextView === 'history' && historyRuns.length === 0) {
      void loadHistory()
    }
    if (nextView === 'system') {
      void refreshDashboard()
    }
  }

  function toggleSidebar() {
    setSidebarCollapsed((current) => {
      const next = !current
      window.localStorage.setItem(
        'material-inspector-sidebar',
        next ? 'collapsed' : 'expanded',
      )
      return next
    })
  }

  function addFiles(fileList: FileList | File[]) {
    const incoming = Array.from(fileList).filter((file) => file.type.startsWith('image/'))
    if (!incoming.length) {
      setProblem({ message: 'Choose JPG, PNG, WEBP, BMP, or another valid image format.' })
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
        setProblem({ message: `A maximum of ${MAX_FILES} images can be processed in one run.` })
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
    setActiveViews({})
  }

  async function analyze() {
    if (!queue.length || isRunning) return
    setIsRunning(true)
    setProblem(null)
    setResult(null)
    try {
      const payload = await runPrediction(
        queue.map((item) => item.file),
        confidence,
        50,
        pixelAreaCm2,
      )
      displayPrediction(payload)
      setHistoryRuns([])
      void refreshDashboard()
    } catch (requestError) {
      showRequestError(requestError)
    } finally {
      setIsRunning(false)
    }
  }

  function displayPrediction(payload: PredictionRun) {
    setResult(payload)
    setActiveViews(
      Object.fromEntries(payload.images.map((image) => [image.image_id, 'output'])),
    )
    setView('inspect')
    window.setTimeout(() => {
      document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }

  async function loadHistory(selectedId?: string) {
    setHistoryLoading(true)
    try {
      const runs = await getHistoryRuns()
      setHistoryRuns(runs)
      const target = selectedId ?? historyDetail?.run_id ?? runs[0]?.run_id
      if (target) await loadHistoryDetail(target)
      if (!target) setHistoryDetail(null)
    } catch (requestError) {
      showRequestError(requestError)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function loadHistoryDetail(runId: string) {
    setDetailLoading(true)
    try {
      const detail = await getHistoryRun(runId)
      setHistoryDetail(detail)
      setActiveViews(
        Object.fromEntries(
          detail.images.map((image) => [image.image_id, image.output_url ? 'output' : 'input']),
        ),
      )
    } catch (requestError) {
      showRequestError(requestError)
    } finally {
      setDetailLoading(false)
    }
  }

  async function refreshDashboard() {
    setDashboardLoading(true)
    try {
      const payload = await getDashboardSummary()
      setDashboard(payload)
      setDashboardError(false)
    } catch {
      setDashboardError(true)
    } finally {
      setDashboardLoading(false)
    }
  }

  async function rerunSelected() {
    if (!historyDetail || isRunning) return
    setIsRunning(true)
    try {
      const payload = await rerunHistory(
        historyDetail.run_id,
        confidence,
        50,
        pixelAreaCm2,
      )
      displayPrediction(payload)
      setHistoryRuns([])
      void refreshDashboard()
    } catch (requestError) {
      showRequestError(requestError)
    } finally {
      setIsRunning(false)
    }
  }

  function showRequestError(error: unknown) {
    if (error instanceof ApiError) {
      setProblem(error.problem)
      return
    }
    setProblem({
      message: error instanceof Error ? error.message : 'The request could not be completed.',
    })
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        view={view}
        open={mobileNavOpen}
        collapsed={sidebarCollapsed}
        onSelect={selectView}
        onClose={() => setMobileNavOpen(false)}
        historyCount={dashboard?.total_runs ?? historyRuns.length}
      />

      <div className="app-main">
        <header className="topbar">
          <button
            className="mobile-menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={20} />
          </button>
          <button
            className="desktop-sidebar-toggle"
            type="button"
            title={sidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            aria-label={sidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            onClick={toggleSidebar}
          >
            {sidebarCollapsed ? <ChevronRight size={19} /> : <ChevronLeft size={19} />}
          </button>
          <div className="page-title">
            <strong>{viewTitle(view)}</strong>
            <span>{viewSubtitle(view)}</span>
          </div>
          <ModelStatus health={health} hasError={healthError} />
        </header>

        <main>
          {view === 'inspect' && (
            <InspectionView
              queue={queue}
              confidence={confidence}
              pixelAreaCm2={pixelAreaCm2}
              health={health}
              healthError={healthError}
              isDragging={isDragging}
              isRunning={isRunning}
              result={result}
              activeViews={activeViews}
              categoryCounts={categoryCounts}
              averageConfidence={averageConfidence}
              onAddFiles={addFiles}
              onRemoveFile={removeFile}
              onClear={clearWorkspace}
              onAnalyze={analyze}
              onConfidenceChange={setConfidence}
              onPixelAreaChange={setPixelAreaCm2}
              onDraggingChange={setIsDragging}
              onViewChange={(imageId, next) =>
                setActiveViews((current) => ({ ...current, [imageId]: next }))
              }
            />
          )}

          {view === 'history' && (
            <HistoryView
              runs={filteredHistory}
              detail={historyDetail}
              search={historySearch}
              loading={historyLoading}
              detailLoading={detailLoading}
              rerunning={isRunning}
              activeViews={activeViews}
              onSearch={setHistorySearch}
              onRefresh={() => void loadHistory()}
              onSelect={(runId) => void loadHistoryDetail(runId)}
              onRerun={() => void rerunSelected()}
              onViewChange={(imageId, next) =>
                setActiveViews((current) => ({ ...current, [imageId]: next }))
              }
            />
          )}

          {view === 'system' && (
            <SystemView
              health={health}
              dashboard={dashboard}
              loading={dashboardLoading}
              hasError={dashboardError}
              onRefresh={() => void refreshDashboard()}
            />
          )}
        </main>
      </div>

      {problem && <ProblemDialog problem={problem} onClose={() => setProblem(null)} />}
    </div>
  )
}

function Sidebar({
  view,
  open,
  collapsed,
  onSelect,
  onClose,
  historyCount,
}: {
  view: ViewName
  open: boolean
  collapsed: boolean
  onSelect: (view: ViewName) => void
  onClose: () => void
  historyCount: number
}) {
  return (
    <>
      <button
        className={`nav-scrim ${open ? 'visible' : ''}`}
        type="button"
        aria-label="Close navigation"
        onClick={onClose}
      />
      <aside className={`sidebar ${open ? 'open' : ''} ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-mark"><ScanLine size={22} /></span>
          <div>
            <strong>Material Inspector</strong>
            <span>Tata Steel</span>
          </div>
        </div>
        <nav className="side-nav">
          <SideNavButton
            active={view === 'inspect'}
            icon={<Home size={18} />}
            label="Inspection"
            collapsed={collapsed}
            onClick={() => onSelect('inspect')}
          />
          <SideNavButton
            active={view === 'history'}
            icon={<History size={18} />}
            label="Run history"
            count={historyCount || undefined}
            collapsed={collapsed}
            onClick={() => onSelect('history')}
          />
          <SideNavButton
            active={view === 'system'}
            icon={<Activity size={18} />}
            label="System"
            collapsed={collapsed}
            onClick={() => onSelect('system')}
          />
        </nav>
        <div className="sidebar-status">
          <ShieldCheck size={18} />
          <div>
            <strong>Audit enabled</strong>
            <span>Inputs and findings retained</span>
          </div>
        </div>
      </aside>
    </>
  )
}

function SideNavButton({
  active,
  icon,
  label,
  count,
  collapsed,
  onClick,
}: {
  active: boolean
  icon: React.ReactNode
  label: string
  count?: number
  collapsed: boolean
  onClick: () => void
}) {
  return (
    <button
      className={active ? 'active' : ''}
      type="button"
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
      {count !== undefined && <b>{count}</b>}
    </button>
  )
}

type InspectionProps = {
  queue: QueuedImage[]
  confidence: number
  pixelAreaCm2: number
  health: HealthResponse | null
  healthError: boolean
  isDragging: boolean
  isRunning: boolean
  result: PredictionRun | null
  activeViews: Record<number, 'input' | 'output'>
  categoryCounts: [string, number][]
  averageConfidence: number | null
  onAddFiles: (files: FileList | File[]) => void
  onRemoveFile: (id: string) => void
  onClear: () => void
  onAnalyze: () => void
  onConfidenceChange: (value: number) => void
  onPixelAreaChange: (value: number) => void
  onDraggingChange: (value: boolean) => void
  onViewChange: (imageId: number, view: 'input' | 'output') => void
}

function InspectionView(props: InspectionProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <>
      <section className="workspace-band">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Inspection workspace</span>
            <h1>Analyze material images</h1>
            <p>Upload one or more waste-pile images for quality validation and detection.</p>
          </div>
          {(props.queue.length > 0 || props.result) && (
            <button className="icon-text-button secondary" type="button" onClick={props.onClear}>
              <RotateCcw size={17} />
              Reset
            </button>
          )}
        </div>

        <div className="workspace-grid">
          <div className="upload-workspace">
            <div
              className={`drop-zone ${props.isDragging ? 'dragging' : ''}`}
              onDragEnter={(event) => {
                event.preventDefault()
                props.onDraggingChange(true)
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                event.preventDefault()
                if (event.currentTarget === event.target) props.onDraggingChange(false)
              }}
              onDrop={(event) => {
                event.preventDefault()
                props.onDraggingChange(false)
                props.onAddFiles(event.dataTransfer.files)
              }}
            >
              <input
                ref={inputRef}
                type="file"
                accept="image/*"
                multiple
                hidden
                onChange={(event) => {
                  if (event.target.files) props.onAddFiles(event.target.files)
                  event.target.value = ''
                }}
              />
              <span className="drop-icon"><Upload size={28} /></span>
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

            <div className="quality-notice">
              <BadgeCheck size={18} />
              <span>Images are checked for blur, exposure, contrast, and resolution before detection.</span>
            </div>

            <div className="queue-header">
              <div>
                <h2>Upload queue</h2>
                <span>{props.queue.length} of {MAX_FILES} selected</span>
              </div>
              {props.queue.length > 0 && (
                <button className="icon-button" type="button" title="Clear queue" onClick={props.onClear}>
                  <Trash2 size={18} />
                </button>
              )}
            </div>

            {props.queue.length === 0 ? (
              <div className="empty-queue">
                <ImageIcon size={24} />
                <span>Selected images will appear here.</span>
              </div>
            ) : (
              <div className="file-grid">
                {props.queue.map((item) => (
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
                      onClick={() => props.onRemoveFile(item.id)}
                    >
                      <X size={16} />
                    </button>
                  </article>
                ))}
              </div>
            )}
          </div>

          <aside className="control-panel">
            <div className="control-heading">
              <Gauge size={20} />
              <h2>Detection settings</h2>
            </div>
            <label className="slider-label" htmlFor="confidence">
              <span>Confidence threshold</span>
              <output>{Math.round(props.confidence * 100)}%</output>
            </label>
            <input
              id="confidence"
              className="confidence-slider"
              type="range"
              min="0.3"
              max="0.9"
              step="0.05"
              value={props.confidence}
              onChange={(event) => props.onConfidenceChange(Number(event.target.value))}
            />
            <div className="range-labels">
              <span>More detections</span>
              <span>More precise</span>
            </div>
            <label className="calibration-control" htmlFor="pixel-area">
              <span><Ruler size={17} /> Image scale</span>
              <div>
                <input
                  id="pixel-area"
                  type="number"
                  min="0.000001"
                  max="100"
                  step="0.001"
                  value={props.pixelAreaCm2}
                  onChange={(event) => props.onPixelAreaChange(Number(event.target.value))}
                />
                <span>cm²/px</span>
              </div>
            </label>
            <div className="model-facts">
              <Fact icon={<Server size={17} />} label="Processor" value={props.health?.device ?? 'Checking'} />
              <Fact icon={<ScanLine size={17} />} label="Classes" value={props.health ? String(props.health.class_count) : '—'} />
              <Fact icon={<ImageIcon size={17} />} label="Input size" value={props.health ? `${props.health.input_size} px` : '640 px'} />
            </div>
            <button
              className="analyze-button"
              type="button"
              disabled={
                !props.queue.length ||
                props.isRunning ||
                props.healthError ||
                props.health?.model_ready === false ||
                props.pixelAreaCm2 <= 0
              }
              onClick={props.onAnalyze}
            >
              {props.isRunning ? <LoaderCircle className="spin" size={19} /> : <Play size={19} />}
              {props.isRunning ? 'Analyzing images' : 'Run detection'}
            </button>
          </aside>
        </div>
      </section>

      {props.result && (
        <ResultsSection
          result={props.result}
          activeViews={props.activeViews}
          categoryCounts={props.categoryCounts}
          averageConfidence={props.averageConfidence}
          onViewChange={props.onViewChange}
        />
      )}
    </>
  )
}

function ResultsSection({
  result,
  activeViews,
  categoryCounts,
  averageConfidence,
  onViewChange,
}: {
  result: PredictionRun
  activeViews: Record<number, 'input' | 'output'>
  categoryCounts: [string, number][]
  averageConfidence: number | null
  onViewChange: (imageId: number, view: 'input' | 'output') => void
}) {
  return (
    <section className="results-band" id="results">
      <div className="section-heading compact">
        <div>
          <span className="eyebrow">Run complete</span>
          <h2>Inspection results</h2>
          <p>Run {result.run_id.slice(0, 8)} · {formatDuration(result.duration_ms)}</p>
        </div>
        <span className="success-mark"><CheckCircle2 size={18} /> Processed</span>
      </div>
      <div className="metric-row">
        <Metric label="Images" value={String(result.images.length)} />
        <Metric label="Detections" value={String(result.total_detections)} />
        <Metric label="Expected pile range" value={formatWeightRange(result.expected_weight_min_kg, result.expected_weight_max_kg)} />
        <Metric label="Average confidence" value={averageConfidence === null ? '—' : `${Math.round(averageConfidence * 100)}%`} />
        <Metric label="Threshold" value={`${Math.round(result.confidence_threshold * 100)}%`} />
      </div>
      <Distribution counts={categoryCounts} />
      <div className="result-list">
        {result.images.map((image, index) => (
          <ResultItem
            key={image.image_id}
            image={image}
            index={index}
            activeView={activeViews[image.image_id] ?? 'output'}
            onViewChange={(next) => onViewChange(image.image_id, next)}
          />
        ))}
      </div>
    </section>
  )
}

function HistoryView({
  runs,
  detail,
  search,
  loading,
  detailLoading,
  rerunning,
  activeViews,
  onSearch,
  onRefresh,
  onSelect,
  onRerun,
  onViewChange,
}: {
  runs: HistoryRun[]
  detail: HistoryRunDetail | null
  search: string
  loading: boolean
  detailLoading: boolean
  rerunning: boolean
  activeViews: Record<number, 'input' | 'output'>
  onSearch: (value: string) => void
  onRefresh: () => void
  onSelect: (runId: string) => void
  onRerun: () => void
  onViewChange: (imageId: number, view: 'input' | 'output') => void
}) {
  const canRerun = Boolean(
    detail?.images.length && detail.images.every((image) => image.input_url),
  )

  return (
    <section className="history-page">
      <div className="page-heading-row">
        <div>
          <span className="eyebrow">Stored inspections</span>
          <h1>Run history</h1>
          <p>Review previous inputs, annotated findings, confidence, and weight ranges.</p>
        </div>
        <button className="icon-text-button secondary" type="button" onClick={onRefresh}>
          <RefreshCw className={loading ? 'spin' : ''} size={17} />
          Refresh
        </button>
      </div>

      <div className="history-shell">
        <aside className="history-index">
          <label className="search-box">
            <Search size={16} />
            <input
              value={search}
              placeholder="Search runs"
              onChange={(event) => onSearch(event.target.value)}
            />
          </label>
          <div className="history-list">
            {loading && runs.length === 0 && <LoadingState label="Loading records" />}
            {!loading && runs.length === 0 && (
              <div className="history-empty"><Database size={24} /><span>No matching records.</span></div>
            )}
            {runs.map((run) => (
              <button
                className={`history-run ${detail?.run_id === run.run_id ? 'active' : ''}`}
                type="button"
                key={run.run_id}
                onClick={() => onSelect(run.run_id)}
              >
                <div className="history-thumb">
                  {run.preview_output_url ?? run.preview_input_url ? (
                    <img src={run.preview_output_url ?? run.preview_input_url ?? ''} alt="" />
                  ) : (
                    <Database size={20} />
                  )}
                </div>
                <div>
                  <strong>{run.preview_filename ?? `Run ${run.run_id.slice(0, 8)}`}</strong>
                  <span>{formatDateTime(run.created_at)}</span>
                  <small>{run.total_detections} detections · {formatWeightRange(run.expected_weight_min_kg, run.expected_weight_max_kg)}</small>
                </div>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </aside>

        <div className="history-detail">
          {detailLoading && <LoadingState label="Loading inspection" />}
          {!detailLoading && !detail && (
            <div className="detail-empty"><Database size={30} /><span>Select a stored run.</span></div>
          )}
          {!detailLoading && detail && (
            <>
              <div className="history-detail-header">
                <div>
                  <span className="eyebrow">{formatDateTime(detail.created_at)}</span>
                  <h2>Inspection {detail.run_id.slice(0, 8)}</h2>
                  <p>{detail.image_count} images · {detail.total_detections} detections</p>
                </div>
                <button
                  className="icon-text-button primary"
                  type="button"
                  title={canRerun ? 'Run detection again' : 'Original input image is unavailable'}
                  onClick={onRerun}
                  disabled={rerunning || !canRerun}
                >
                  {rerunning ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}
                  Run again
                </button>
              </div>
              <div className="history-metrics">
                <Metric label="Expected range" value={formatWeightRange(detail.expected_weight_min_kg, detail.expected_weight_max_kg)} />
                <Metric label="Threshold" value={`${Math.round(detail.confidence_threshold * 100)}%`} />
                <Metric label="Image scale" value={`${(detail.pixel_area_cm2 ?? DEFAULT_PIXEL_AREA_CM2).toFixed(3)} cm²/px`} />
                <Metric label="Duration" value={detail.duration_ms === null ? '—' : formatDuration(detail.duration_ms)} />
              </div>
              {detail.source_run_id && (
                <div className="lineage-note">
                  <History size={16} />
                  Redetection of run {detail.source_run_id.slice(0, 8)}
                </div>
              )}
              {!canRerun && (
                <div className="lineage-note warning">
                  <AlertCircle size={16} />
                  Rerun unavailable because an original input file was removed.
                </div>
              )}
              <div className="history-result-list">
                {detail.images.map((image, index) => (
                  <ResultItem
                    key={image.image_id}
                    image={image}
                    index={index}
                    activeView={activeViews[image.image_id] ?? 'output'}
                    onViewChange={(next) => onViewChange(image.image_id, next)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function SystemView({
  health,
  dashboard,
  loading,
  hasError,
  onRefresh,
}: {
  health: HealthResponse | null
  dashboard: DashboardSummary | null
  loading: boolean
  hasError: boolean
  onRefresh: () => void
}) {
  return (
    <section className="system-page">
      <div className="page-heading-row">
        <div>
          <span className="eyebrow">Operations dashboard</span>
          <h1>System activity</h1>
          <p>Inspection volume, detected objects, material mix, and service readiness.</p>
        </div>
        <button className="icon-text-button secondary" type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw className={loading ? 'spin' : ''} size={17} />
          Refresh
        </button>
      </div>

      {hasError && (
        <div className="dashboard-error">
          <AlertCircle size={18} />
          <span>Dashboard metrics could not be loaded. The detector can still be used.</span>
        </div>
      )}

      {loading && !dashboard && <LoadingState label="Loading system activity" />}

      {dashboard && (
        <>
          <div className="dashboard-kpis">
            <DashboardMetric
              icon={<History size={20} />}
              label="Inspections to date"
              value={formatCount(dashboard.total_runs)}
              detail={`${formatCount(dashboard.completed_runs)} completed`}
            />
            <DashboardMetric
              icon={<Activity size={20} />}
              label="Inspections today"
              value={formatCount(dashboard.today_runs)}
              detail={formatShortDate(dashboard.today_label)}
              accent="coral"
            />
            <DashboardMetric
              icon={<ScanLine size={20} />}
              label="Objects detected"
              value={formatCount(dashboard.total_detections)}
              detail="Across all stored inspections"
            />
            <DashboardMetric
              icon={<TargetIcon />}
              label="Objects today"
              value={formatCount(dashboard.today_detections)}
              detail={`${formatCount(dashboard.today_images)} images processed`}
              accent="coral"
            />
          </div>

          <div className="dashboard-supporting">
            <DashboardStat label="Images processed" value={formatCount(dashboard.total_images)} />
            <DashboardStat label="Success rate" value={`${dashboard.success_rate.toFixed(1)}%`} />
            <DashboardStat
              label="Average run time"
              value={dashboard.average_duration_ms === null ? '—' : formatDuration(dashboard.average_duration_ms)}
            />
            <DashboardStat label="Failed runs" value={formatCount(dashboard.failed_runs)} warning={dashboard.failed_runs > 0} />
          </div>

          <div className="dashboard-visuals">
            <section className="dashboard-panel activity-panel">
              <header>
                <div>
                  <span className="eyebrow">Seven-day movement</span>
                  <h2>Inspection activity</h2>
                </div>
                <span>{dashboard.timezone}</span>
              </header>
              <ActivityChart points={dashboard.daily_activity} />
            </section>

            <section className="dashboard-panel material-panel">
              <header>
                <div>
                  <span className="eyebrow">Lifetime object mix</span>
                  <h2>Detected materials</h2>
                </div>
                <span>{formatCount(dashboard.total_detections)} objects</span>
              </header>
              <MaterialMix materials={dashboard.material_counts} />
            </section>
          </div>

          <div className="system-grid">
            <SystemPanel icon={<Server size={20} />} title="Detector readiness">
              <SystemRow label="Status" value={health?.model_ready ? 'Ready' : 'Unavailable'} />
              <SystemRow label="Checkpoint" value={health?.model_name ?? 'Checking'} />
              <SystemRow label="Processor" value={health?.device ?? 'Checking'} />
              <SystemRow label="Input size" value={health ? `${health.input_size}px` : '640px'} />
            </SystemPanel>
            <SystemPanel icon={<ShieldCheck size={20} />} title="Inspection safeguards">
              <SystemRow label="Image validation" value="Active" />
              <SystemRow label="Audit database" value="SQLite" />
              <SystemRow label="Weight output" value="Expected range" />
              <SystemRow label="Material classes" value={health ? String(health.class_count) : '—'} />
            </SystemPanel>
          </div>

          <p className="dashboard-freshness">
            Updated {formatDateTime(dashboard.generated_at)}
          </p>
        </>
      )}
    </section>
  )
}

function DashboardMetric({
  icon,
  label,
  value,
  detail,
  accent = 'green',
}: {
  icon: React.ReactNode
  label: string
  value: string
  detail: string
  accent?: 'green' | 'coral'
}) {
  return (
    <article className={`dashboard-metric ${accent}`}>
      <div className="dashboard-metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  )
}

function DashboardStat({
  label,
  value,
  warning = false,
}: {
  label: string
  value: string
  warning?: boolean
}) {
  return (
    <div className={`dashboard-stat ${warning ? 'warning' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ActivityChart({ points }: { points: DashboardSummary['daily_activity'] }) {
  const maximum = Math.max(1, ...points.map((point) => point.runs))
  return (
    <div className="activity-chart" aria-label="Inspection runs over the last seven days">
      {points.map((point) => (
        <div
          className="activity-column"
          key={point.date}
          title={`${point.runs} inspections, ${point.images} images, ${point.detections} objects`}
        >
          <div className="activity-count">{point.runs}</div>
          <div className="activity-track">
            <span
              className={point.date === points.at(-1)?.date ? 'today' : ''}
              style={{ height: `${point.runs ? Math.max(12, (point.runs / maximum) * 100) : 0}%` }}
            />
          </div>
          <strong>{point.label}</strong>
          <small>{point.detections} obj</small>
        </div>
      ))}
    </div>
  )
}

function MaterialMix({ materials }: { materials: DashboardSummary['material_counts'] }) {
  if (!materials.length) {
    return <div className="dashboard-empty"><Database size={22} /><span>No detections recorded yet.</span></div>
  }
  const maximum = Math.max(1, materials[0].count)
  return (
    <div className="material-mix">
      {materials.slice(0, 7).map((material) => (
        <div className="material-mix-row" key={material.label}>
          <span>{displayLabel(material.label)}</span>
          <div><i style={{ width: `${Math.max(5, (material.count / maximum) * 100)}%` }} /></div>
          <strong>{formatCount(material.count)}</strong>
        </div>
      ))}
    </div>
  )
}

function TargetIcon() {
  return <CircleGauge size={20} />
}

function SystemPanel({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <article className="system-panel">
      <header>{icon}<h2>{title}</h2></header>
      <div>{children}</div>
    </article>
  )
}

function SystemRow({ label, value }: { label: string; value: string }) {
  return <div className="system-row"><span>{label}</span><strong>{value}</strong></div>
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
  const activeUrl = activeView === 'input' ? image.input_url : image.output_url

  return (
    <article className="result-item">
      <div className="result-toolbar">
        <div>
          <span>Image {index + 1}</span>
          <strong>{image.filename}</strong>
        </div>
        <div className="result-actions">
          {image.quality && (
            <span className="quality-score" title={`Sharpness ${image.quality.blur_score.toFixed(1)}`}>
              <BadgeCheck size={15} />
              Quality {Math.round(image.quality.score)}%
            </span>
          )}
          <div className="segmented-control">
            <button
              type="button"
              className={activeView === 'input' ? 'active' : ''}
              disabled={!image.input_url}
              onClick={() => onViewChange('input')}
            >
              <ImageIcon size={16} /> Input
            </button>
            <button
              type="button"
              className={activeView === 'output' ? 'active' : ''}
              disabled={!image.output_url}
              onClick={() => onViewChange('output')}
            >
              <ScanLine size={16} /> Detection
            </button>
          </div>
          {image.output_url && (
            <a className="icon-button" href={image.output_url} download title="Download annotated image">
              <Download size={18} />
            </a>
          )}
        </div>
      </div>
      <div className="result-body">
        <figure className="image-viewer">
          {activeUrl ? (
            <img
              src={activeUrl}
              alt={activeView === 'input' ? `Uploaded ${image.filename}` : `Detected materials in ${image.filename}`}
            />
          ) : (
            <div className="missing-image">
              <ImageIcon size={28} />
              <strong>Stored image unavailable</strong>
              <span>The database record and findings are still available.</span>
            </div>
          )}
          <figcaption>
            {image.width} × {image.height}px
            <span>{activeView === 'input' ? 'Original input' : 'Annotated output'}</span>
          </figcaption>
        </figure>
        <div className="detection-panel">
          <div className="detection-summary">
            <div><span>Objects found</span><strong>{image.detection_count}</strong></div>
            <div><span>Mean confidence</span><strong>{image.mean_confidence === null ? '—' : `${Math.round(image.mean_confidence * 100)}%`}</strong></div>
            <div><span>Expected weight</span><strong>{formatWeightRange(image.expected_weight_min_kg, image.expected_weight_max_kg)}</strong></div>
          </div>
          {image.detections.length === 0 ? (
            <div className="no-detections"><AlertCircle size={20} /><span>No object passed the selected threshold.</span></div>
          ) : (
            <div className="detection-list">
              {image.detections.map((detection, detectionIndex) => (
                <div className="detection-row" key={`${detection.label}-${detectionIndex}`}>
                  <span className="detection-index">{detectionIndex + 1}</span>
                  <div>
                    <strong>{displayLabel(detection.label)}</strong>
                    <span>{formatDetectionMethod(detection.weight_method)}</span>
                  </div>
                  <div className="detection-values">
                    <b>{Math.round(detection.confidence * 100)}%</b>
                    <span>{formatWeightRange(detection.expected_weight_min_kg ?? 0, detection.expected_weight_max_kg ?? 0)}</span>
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

function Distribution({ counts }: { counts: [string, number][] }) {
  if (!counts.length) return null
  return (
    <div className="distribution">
      <h3>Detected material distribution</h3>
      <div className="distribution-list">
        {counts.map(([label, count]) => (
          <div className="distribution-item" key={label}>
            <span>{displayLabel(label)}</span>
            <div className="distribution-track"><span style={{ width: `${Math.max(8, (count / counts[0][1]) * 100)}%` }} /></div>
            <strong>{count}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}

function ProblemDialog({ problem, onClose }: { problem: ApiProblem; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="problem-dialog" role="alertdialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-icon"><AlertCircle size={24} /></div>
        <div className="dialog-copy">
          <span>Inspection stopped</span>
          <h2>{problem.code === 'image_quality_failed' ? 'Image quality is not sufficient' : 'Unable to continue'}</h2>
          <p>{problem.message}</p>
        </div>
        <button className="icon-button dialog-close" type="button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        {problem.images && (
          <div className="quality-failures">
            {problem.images.map((image) => (
              <div key={image.filename}>
                <strong>{image.filename}</strong>
                <span>Quality score {Math.round(image.score)}%</span>
                <ul>{image.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
              </div>
            ))}
          </div>
        )}
        <button className="icon-text-button primary dialog-action" type="button" onClick={onClose}>Choose another image</button>
      </div>
    </div>
  )
}

function LoadingState({ label }: { label: string }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={22} /><span>{label}</span></div>
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
  return <div className="fact">{icon}<span>{label}</span><strong>{value}</strong></div>
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function materialCounts(images: ImageResult[]): [string, number][] {
  const counts = new Map<string, number>()
  images.forEach((image) => image.detections.forEach((detection) => {
    counts.set(detection.label, (counts.get(detection.label) ?? 0) + 1)
  }))
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

function calculateAverageConfidence(images: ImageResult[]) {
  const scores = images.flatMap((image) => image.detections.map((item) => item.confidence))
  return scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null
}

function viewTitle(view: ViewName) {
  return view === 'inspect' ? 'Inspection workspace' : view === 'history' ? 'Previous runs' : 'System overview'
}

function viewSubtitle(view: ViewName) {
  return view === 'inspect' ? 'Quality-controlled material analysis' : view === 'history' ? 'Inputs, predictions, and findings' : 'Model and service status'
}

function displayLabel(label: string) {
  return label.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDetectionMethod(method: string | null) {
  if (!method) return 'Bounding-box estimate'
  if (method.includes('foreground_refined')) return 'Foreground-refined area'
  if (method.includes('geometry_refined')) return 'Geometry-refined area'
  if (method.includes('calibrated')) return 'Calibrated box area'
  return 'Bounding-box area'
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
  if (weightMaxKg < 1) return `${Math.round(weightMinKg * 1000)}–${Math.round(weightMaxKg * 1000)} g`
  return `${weightMinKg.toFixed(2)}–${weightMaxKg.toFixed(2)} kg`
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata',
  }).format(new Date(`${value}T00:00:00+05:30`))
}

function formatCount(value: number) {
  return new Intl.NumberFormat().format(value)
}

export default App
