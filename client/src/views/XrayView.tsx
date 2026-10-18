import { useEffect, useState } from 'react'
import { XrayBayOverview } from '@/components/XrayBayOverview'
import { XrayMap } from '@/components/XrayMap'
import { XrayComparison } from '@/components/XrayComparison'
import { XrayProfile } from '@/components/XrayProfile'
import type { SatelliteModel, XrayMetadata, XrayObservation, XraySegment, XrayStage } from '@/models/xray'
import { fetchXrayMetadata, fetchXraySegment, fetchXraySurvey, xrayResourceUrl } from '@/services/xrayService'
import './XrayView.css'

const STAGES: { id: XrayStage; label: string; detail: string }[] = [
  { id: 'hidden', label: 'Withhold', detail: 'Hide part of the boat track from the model.' },
  { id: 'location', label: 'Estimate', detail: 'Fill the gap using nearby locations only.' },
  { id: 'satellite', label: 'Add imagery', detail: 'Same test with satellite reflectance included.' },
  { id: 'reveal', label: 'Compare', detail: 'Show estimates next to what the boat measured.' },
]

const date = (value: string) => new Date(value).toLocaleString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' UTC'

export function XrayView() {
  const [metadata, setMetadata] = useState<XrayMetadata | null>(null)
  const [mode, setMode] = useState<'bay' | 'experiment' | 'survey'>(() => window.location.hash.includes('segment=') ? 'experiment' : 'bay')
  const [segmentId, setSegmentId] = useState(() => {
    const value = Number(new URLSearchParams(window.location.hash.split('?')[1]).get('segment'))
    return [17, 31, 32].includes(value) ? value : 32
  })
  const [stage, setStage] = useState<XrayStage>('hidden')
  const [segment, setSegment] = useState<XraySegment | null>(null)
  const [satelliteModel, setSatelliteModel] = useState<SatelliteModel>('gp_resid')
  const [survey, setSurvey] = useState<XrayObservation[]>([])
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [layerId, setLayerId] = useState('none')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchXrayMetadata(controller.signal).then(setMetadata).catch(() => {
      if (!controller.signal.aborted) setError('Survey data could not be loaded. Try again in a moment.')
    })
    return () => controller.abort()
  }, [attempt])

  useEffect(() => {
    const controller = new AbortController()
    if (mode === 'experiment') {
      fetchXraySegment(segmentId, stage, controller.signal).then(setSegment).catch(() => {
        if (!controller.signal.aborted) setError('The saved holdout case is unavailable. No substitute predictions are shown.')
      }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    } else {
      fetchXraySurvey(controller.signal).then(points => {
        setSurvey(points)
        setCursor(points.length - 1)
      }).catch(() => {
        if (!controller.signal.aborted) setError('The historical observation export is unavailable.')
      }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }
    return () => controller.abort()
  }, [mode, segmentId, stage, attempt])

  useEffect(() => {
    if (!playing || mode !== 'survey') return
    const timer = window.setInterval(() => setCursor(value => {
      if (value >= survey.length - 1) { setPlaying(false); return value }
      return Math.min(value + 15, survey.length - 1)
    }), 150)
    return () => window.clearInterval(timer)
  }, [playing, mode, survey.length])

  function changeStage(next: XrayStage) {
    if (next === stage) return
    setLoading(true)
    setError(null)
    setSegment(null)
    setStage(next)
  }

  function changeMode(next: 'bay' | 'experiment' | 'survey') {
    if (next !== mode) { setLoading(true); setError(null); setSegment(null) }
    setMode(next); setLayerId('none'); setPlaying(false)
  }

  const activeIndex = STAGES.findIndex(s => s.id === stage)
  const activeLayer = metadata?.layers.find(l => l.id === layerId && (mode === 'survey' || l.scope !== 'full_fit_not_holdout'))
  const readySegment = segment?.id === segmentId && segment.stage === stage ? segment : null
  const selectedObservation = survey[cursor]
  const metric = readySegment?.metrics
  const improvement = metric ? (1 - metric[satelliteModel].mae / metric.rf_xy.mae) * 100 : null

  return <div className="xray">
    <section className="xray-intro">
      <div>
        <p className="eyebrow">2025 boat fluorescence survey</p>
        <h2>{mode === 'bay' ? 'Fluorescence across the bay' : 'Can we fill a missing transect?'}</h2>
        <p>{mode === 'bay'
          ? 'Map of pigment fluorescence from the research vessel, plus a test where part of the track is hidden from the model.'
          : 'Choose a transect, estimate fluorescence with and without satellite imagery, then compare to boat measurements.'}</p>
      </div>
      <div className="xray-tag"><strong>Jun 30 – Jul 1, 2025</strong><span>Archived study</span></div>
    </section>
    <div className="xray-mode" aria-label="Replay mode">
      <button className={`btn ${mode === 'bay' ? 'btn--primary' : ''}`} aria-pressed={mode === 'bay'} onClick={() => changeMode('bay')}>Bay map</button>
      <button className={`btn ${mode === 'experiment' ? 'btn--primary' : ''}`} aria-pressed={mode === 'experiment'} onClick={() => changeMode('experiment')}>Gap test</button>
      <button className={`btn ${mode === 'survey' ? 'btn--primary' : ''}`} aria-pressed={mode === 'survey'} onClick={() => changeMode('survey')}>Boat track</button>
      <span className="muted">{metadata?.observation_count.toLocaleString() ?? '…'} samples · fluorescence (RFU)</span>
    </div>
    {error && <div className="card xray-error" role="alert"><p>{error}</p><button className="btn" onClick={() => { setLoading(true); setError(null); setAttempt(v => v + 1) }}>Retry loading</button></div>}
    {mode === 'experiment' ? <>
      <div className="xray-row xray-controls">
        <label>Transect <select value={segmentId} onChange={event => { setLoading(true); setError(null); setSegment(null); setSegmentId(Number(event.target.value)); setStage('hidden') }}>
          {(metadata?.cases ?? [{ id: 32, label: 'After plume' }, { id: 31, label: 'Poor fit' }, { id: 17, label: 'Typical' }]).map(c => <option key={c.id} value={c.id}>{c.label} (segment {c.id})</option>)}
        </select></label>
        <label>Imagery<select value={satelliteModel} onChange={e => setSatelliteModel(e.target.value as SatelliteModel)}>
          <option value="gp_resid">Trend + smoothing (research)</option><option value="rf_xysat">Location + satellite (main)</option>
        </select></label>
      </div>
      <ol className="xray-steps" aria-label="Hide predict reveal steps">
        {STAGES.map((s, i) => <li key={s.id}><button aria-label={s.label} aria-current={stage === s.id ? 'step' : undefined}
          className={stage === s.id ? 'is-active' : i < activeIndex ? 'is-done' : ''} onClick={() => changeStage(s.id)}>
          <span>{i + 1}</span>{s.label}</button></li>)}
      </ol>
      {loading || !readySegment ? <div className="card xray-map-placeholder" role="status">{error ? 'Research map unavailable' : 'Loading recorded holdout…'}</div> :
        <XrayComparison key={segmentId} segment={readySegment} satelliteModel={satelliteModel} bayBounds={metadata?.bay?.layers[0]?.bounds} />}
      <div className="xray-workspace">
        {readySegment && <XrayProfile segment={readySegment} satelliteModel={satelliteModel} />}
        <aside className="xray-panel">
          <section className="card">
            <p className="eyebrow">Step {activeIndex + 1} of 4</p><h3>How close was the estimate?</h3>
            <p className="muted">{satelliteModel === 'gp_resid'
              ? 'Research approach: satellite trend plus spatial smoothing.'
              : 'Main comparison: location-only method plus satellite bands.'}</p>
            {metric && improvement !== null ? <div className="xray-metrics" aria-live="polite">
              <div><span>Location only</span><strong>{metric.rf_xy.mae.toFixed(2)} <small>RFU avg. error</small></strong></div>
              <div><span>With imagery</span><strong>{metric[satelliteModel].mae.toFixed(2)} <small>RFU avg. error</small></strong></div>
              <p className={improvement > 0 ? 'xray-gain' : 'xray-loss'}>{Math.abs(improvement).toFixed(1)}% {improvement > 0 ? 'smaller' : 'larger'} error on this transect</p>
            </div> : <p className="xray-sealed">Errors appear after the Compare step.</p>}
            {activeIndex < STAGES.length - 1 ? <button className="btn btn--primary xray-next" disabled={loading} onClick={() => changeStage(STAGES[activeIndex + 1].id)}>{STAGES[activeIndex + 1].label} →</button>
              : <a
                  className="btn btn--primary xray-next"
                  href={`#/bfi?q=${encodeURIComponent('How do phosphorus and temperature drivers relate to bloom favorability in Green Bay?')}`}
                >
                  Ask about bloom drivers →
                </a>}
          </section>
          <section className="card xray-protocol"><h3>What was hidden?</h3>
            <p>5 km of the boat track and nearby measurements so the model cannot see the answer.</p>
            {readySegment && <p><strong>{readySegment.training.length.toLocaleString()}</strong> training points · <strong>{readySegment.matched_count}/{readySegment.total_count}</strong> compared on the withheld section.</p>}
            <p className="muted">All methods use the same withheld data. Compare shows saved estimates—not a new training run.</p>
          </section>
        </aside>
      </div>
      {readySegment?.metrics && <details className="card"><summary>All methods on this transect</summary><div className="xray-table-wrap"><table className="xray-table"><thead><tr><th>Method</th><th>Avg. error (RFU)</th><th>Bias (RFU)</th></tr></thead><tbody>
        {Object.entries(readySegment.metrics).map(([key, value]) => <tr key={key}><td>{metadata?.models[key as keyof typeof metadata.models] ?? key}</td><td>{value.mae.toFixed(3)}</td><td>{value.bias.toFixed(3)}</td></tr>)}
      </tbody></table></div><p className="muted">Lower average error is better. Results apply to this transect only—not the whole bay.</p></details>}
      {readySegment && <details className="card"><summary>Inspect timestamps and satellite matches</summary><div className="xray-table-wrap"><table className="xray-table"><thead><tr><th>Bin</th><th>Boat observation (UTC)</th><th>Satellite scene</th><th>Image − boat (h)</th></tr></thead><tbody>
        {readySegment.points.map(p => <tr key={p.id}><td>{p.id}</td><td>{date(p.observed_at)}</td><td>{p.scene_id}</td><td>{p.lag_hours.toFixed(2)}</td></tr>)}
      </tbody></table></div><p className="muted">Negative lag means the image was acquired before the boat measurement. Matching allows up to 24 hours; images are not simultaneous with every observation.</p></details>}
    </> : mode === 'bay' ? metadata && <XrayBayOverview metadata={metadata} observations={survey} /> : <section className="card xray-map-card">
      <div className="xray-map-heading"><div><h3>Follow the research vessel</h3><p className="muted">Real measurements; timestamps and overnight gaps are preserved.</p></div>
        <label>Research overlay<select value={layerId} onChange={e => setLayerId(e.target.value)}><option value="none">Measurements only</option>{metadata?.layers.map(l => <option key={l.id} value={l.id}>{l.title}</option>)}</select></label></div>
      {activeLayer && <div className="xray-layer-note"><strong>{activeLayer.scope === 'full_fit_not_holdout' ? 'Full-survey fit — NOT held-out validation.' : 'Satellite input context — NOT measured fluorescence.'}</strong>
        <p>{activeLayer.title} · {activeLayer.acquired_at} · display range {activeLayer.display_min.toFixed(3)}–{activeLayer.display_max.toFixed(3)} {activeLayer.units} (2nd–98th percentiles).</p>
        <p>{activeLayer.scope === 'full_fit_not_holdout' ? 'This raster uses all matched training bins. It is excluded from the hide/reveal experiment. Blank areas have no valid pixels or are beyond 3 km of training evidence.' : 'This July 1 scene is context only; individual holdout bins may match another scene. Blank pixels are masked.'}</p></div>}
      {survey.length > 0 && !loading ? <XrayMap training={survey.slice(0, cursor + 1)} target={[]} display={selectedObservation ? [selectedObservation] : []}
        focusKey="whole-survey" highlightId={selectedObservation?.id} layer={activeLayer} /> : <div className="xray-map-placeholder">{error ? 'Survey unavailable' : 'Loading survey…'}</div>}
      <div className="xray-timeline">
        <div className="xray-row"><button className="btn btn--primary" disabled={!survey.length} onClick={() => { if (cursor >= survey.length - 1) setCursor(0); setPlaying(!playing) }}>{playing ? 'Pause survey' : 'Play survey'}</button>
          <output aria-live={playing ? 'off' : 'polite'}>{selectedObservation && <>{date(selectedObservation.observed_at)} · <strong>{selectedObservation.value.toFixed(2)} RFU</strong> · bin {cursor + 1}/{survey.length}</>}</output></div>
        <label htmlFor="survey-time">Vessel observation timeline (UTC)</label><input id="survey-time" type="range" min={0} max={Math.max(0, survey.length - 1)} value={cursor} onChange={e => { setPlaying(false); setCursor(Number(e.target.value)) }} />
        <div className="xray-row muted"><span>{metadata && date(metadata.start)}</span><span>{metadata && date(metadata.end)}</span></div>
      </div>
    </section>}
    {metadata && <section className="card xray-context"><div><p className="eyebrow">Whole-study summary</p><h3>Does satellite imagery help overall?</h3>
      <p>Across withheld tests, the main satellite approach changed average error by about {Math.abs(metadata.overall.primary_comparison.pooled_MAE_change_pct).toFixed(1)}% ({metadata.overall.folds} transects). Uncertainty spans {metadata.overall.primary_comparison.fold_bootstrap_95ci_pct.map(v => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`).join(' to ')}—improvement is not guaranteed bay-wide.</p>
      <p>The research smoothing variant did worse than location-only on {metadata.overall.diagnostic_comparison.folds_worse} of {metadata.overall.folds} transects.</p>
      <button className="btn" onClick={() => { if (segmentId !== 31 || stage !== 'hidden' || mode !== 'experiment') { setLoading(true); setError(null); setSegment(null) } setMode('experiment'); setSegmentId(31); setStage('hidden'); setLayerId('none'); setPlaying(false) }}>See a transect where imagery did not help →</button>
    </div><div><h3>Reading fluorescence (RFU)</h3><p>{metadata.limitations[0]}</p><p>{metadata.limitations[1]}</p><p className="muted">Archived survey only—not today’s conditions or a bloom forecast.</p></div></section>}
    {metadata && <section className="card"><h3>Data &amp; references</h3><p className="muted">{metadata.aggregation}. USGS FLAMe survey (Loken et al., 2026).</p><div className="xray-sources">{metadata.sources.map(s => <a key={s.id} href={xrayResourceUrl(s.url)} target="_blank" rel="noreferrer">{s.title} ↗</a>)}</div></section>}
  </div>
}
