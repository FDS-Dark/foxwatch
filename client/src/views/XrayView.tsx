import { useEffect, useState } from 'react'
import { XrayBayOverview } from '@/components/XrayBayOverview'
import { XrayMap } from '@/components/XrayMap'
import { XrayComparison } from '@/components/XrayComparison'
import { XrayProfile } from '@/components/XrayProfile'
import type { SatelliteModel, XrayMetadata, XrayObservation, XraySegment, XrayStage } from '@/models/xray'
import { fetchXrayMetadata, fetchXraySegment, fetchXraySurvey, xrayResourceUrl } from '@/services/xrayService'
import './XrayView.css'

const STAGES: { id: XrayStage; label: string; detail: string }[] = [
  { id: 'hidden', label: 'Hide', detail: 'Remove the segment and its neighboring measurements.' },
  { id: 'location', label: 'Predict from location', detail: 'Reconstruct the missing segment using geographic coordinates.' },
  { id: 'satellite', label: 'Add satellite', detail: 'Compare a reconstruction that also uses satellite reflectance.' },
  { id: 'reveal', label: 'Reveal measurements', detail: 'Compare saved predictions against the withheld boat measurements.' },
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
      if (!controller.signal.aborted) setError('Research data could not be loaded. Check that the FoxWatch API is running.')
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
      <div><p className="eyebrow">A real survey. A missing piece. A measurable answer.</p>
        <h2>{mode === 'bay' ? 'See between the measurements.' : 'What did the boat miss?'}</h2>
        <p>{mode === 'bay' ? 'Explore a continuous fluorescence reconstruction, then put the model to the test with a hidden boat transect.' : 'Hide a stretch of the Green Bay survey, reconstruct it, then reveal what was actually measured.'}</p>
      </div>
      <div className="xray-tag"><strong>JUN 30 — JUL 1, 2025</strong><span>USGS FLAMe · historical research</span></div>
    </section>
    <div className="xray-mode" aria-label="Replay mode">
      <button className={`btn ${mode === 'bay' ? 'btn--primary' : ''}`} aria-pressed={mode === 'bay'} onClick={() => changeMode('bay')}>Bay gradient</button>
      <button className={`btn ${mode === 'experiment' ? 'btn--primary' : ''}`} aria-pressed={mode === 'experiment'} onClick={() => changeMode('experiment')}>X-Ray experiment</button>
      <button className={`btn ${mode === 'survey' ? 'btn--primary' : ''}`} aria-pressed={mode === 'survey'} onClick={() => changeMode('survey')}>Explore measured survey</button>
      <span className="muted">{metadata?.observation_count.toLocaleString() ?? '…'} measured bins · 100 m along-track medians · RFU</span>
    </div>
    {error && <div className="card xray-error" role="alert"><p>{error}</p><button className="btn" onClick={() => { setLoading(true); setError(null); setAttempt(v => v + 1) }}>Retry loading</button></div>}
    {mode === 'experiment' ? <>
      <div className="xray-row xray-controls">
        <label>Research case <select value={segmentId} onChange={event => { setLoading(true); setError(null); setSegment(null); setSegmentId(Number(event.target.value)); setStage('hidden') }}>
          {(metadata?.cases ?? [{ id: 32, label: 'Plume recovery' }, { id: 31, label: 'Failure case' }, { id: 17, label: 'Typical case' }]).map(c => <option key={c.id} value={c.id}>Segment {c.id} · {c.label}</option>)}
        </select></label>
        <label>Satellite model<select value={satelliteModel} onChange={e => setSatelliteModel(e.target.value as SatelliteModel)}>
          <option value="gp_resid">Satellite trend + GP · diagnostic</option><option value="rf_xysat">Location + satellite RF · primary</option>
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
            <p className="eyebrow">The comparison</p><h3>Location vs satellite</h3>
            <p className="muted">{satelliteModel === 'gp_resid' ? 'A linear satellite trend plus a spatial Gaussian process. The striking segment-32 result comes from this diagnostic model.' : 'The primary comparison adds satellite bands to the same random-forest architecture used by the location-only baseline.'}</p>
            {metric && improvement !== null ? <div className="xray-metrics" aria-live="polite">
              <div><span>Location-only RF error</span><strong>{metric.rf_xy.mae.toFixed(2)} <small>RFU</small></strong></div>
              <div><span>Selected satellite model error</span><strong>{metric[satelliteModel].mae.toFixed(2)} <small>RFU</small></strong></div>
              <p className={improvement > 0 ? 'xray-gain' : 'xray-loss'}>{Math.abs(improvement).toFixed(1)}% {improvement > 0 ? 'lower' : 'higher'} mean absolute error on this segment</p>
            </div> : <p className="xray-sealed">Measurement values and errors stay hidden until Reveal.</p>}
            {activeIndex < STAGES.length - 1 ? <button className="btn btn--primary xray-next" disabled={loading} onClick={() => changeStage(STAGES[activeIndex + 1].id)}>{STAGES[activeIndex + 1].label} →</button>
              : <a className="btn btn--primary xray-next" href={`#/investigate?segment=${segmentId}`}>Explain this result →</a>}
          </section>
          <section className="card xray-protocol"><h3>What was held out?</h3>
            <p>A 5 km segment, its 1 km along-track neighbors, and all measurements within 1.5 km.</p>
            {readySegment && <p><strong>{readySegment.training.length.toLocaleString()}</strong> matched training bins · <strong>{readySegment.matched_count}/{readySegment.total_count}</strong> matched target bins.</p>}
            <p className="muted">Every model uses the same matched bins and exclusion zones. The reveal does not refit a model.</p>
          </section>
        </aside>
      </div>
      {readySegment?.metrics && <details className="card"><summary>All saved models · same withheld measurements</summary><div className="xray-table-wrap"><table className="xray-table"><thead><tr><th>Model</th><th>MAE (RFU)</th><th>Bias (RFU)</th></tr></thead><tbody>
        {Object.entries(readySegment.metrics).map(([key, value]) => <tr key={key}><td>{metadata?.models[key as keyof typeof metadata.models] ?? key}</td><td>{value.mae.toFixed(3)}</td><td>{value.bias.toFixed(3)}</td></tr>)}
      </tbody></table></div><p className="muted">MAE: average absolute error; lower is better. Negative bias means underestimation. These are segment results, not bay-wide performance.</p></details>}
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
    {metadata && <section className="card xray-context"><div><p className="eyebrow">One recovery is not a general result</p><h3>Keep the failure in the story</h3>
      <p>The primary satellite RF reduces pooled MAE by {Math.abs(metadata.overall.primary_comparison.pooled_MAE_change_pct).toFixed(1)}% across {metadata.overall.folds} folds. Its 95% interval for MAE change ({metadata.overall.primary_comparison.fold_bootstrap_95ci_pct.map(v => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`).join(' to ')}) includes no improvement.</p>
      <p>The diagnostic satellite-trend GP is worse than the location-only RF in {metadata.overall.diagnostic_comparison.folds_worse}/{metadata.overall.folds} folds.</p>
      <button className="btn" onClick={() => { if (segmentId !== 31 || stage !== 'hidden' || mode !== 'experiment') { setLoading(true); setError(null); setSegment(null) } setMode('experiment'); setSegmentId(31); setStage('hidden'); setLayerId('none'); setPlaying(false) }}>Try segment 31: the failure case →</button>
    </div><div><h3>What this signal means</h3><p>{metadata.limitations[0]}</p><p>{metadata.limitations[1]}</p><p className="muted">Historical reconstruction · {metadata.model_version}. No current bloom or forecast is implied.</p></div></section>}
    {metadata && <section className="card"><h3>Trace the evidence</h3><p className="muted">{metadata.aggregation}. Data: USGS FLAMe, Loken et al. (2026).</p><div className="xray-sources">{metadata.sources.map(s => <a key={s.id} href={xrayResourceUrl(s.url)} target="_blank" rel="noreferrer">{s.title} ↗</a>)}</div></section>}
  </div>
}
