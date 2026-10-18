import { useEffect, useState } from 'react'
import { XrayLiveMap } from '@/components/XrayLiveMap'
import type { LiveXray } from '@/models/xrayLive'
import type { LatestObservations } from '@/models/observations'
import { fetchLiveXray } from '@/services/xrayService'
import { fetchLatestObservations } from '@/services/observationsService'
import './XrayView.css'
import './XrayLiveView.css'

const date = (value: string, includeTime = false) => new Date(value).toLocaleString(undefined, {
  month: 'short', day: 'numeric', year: 'numeric',
  ...(includeTime ? { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' as const } : {}),
})
const PARAMETERS = [
  { code: '00010', title: 'Water temperature', icon: '°' },
  { code: '00060', title: 'River discharge', icon: '≈' },
  { code: '00300', title: 'Dissolved oxygen', icon: 'O₂' },
]

export function XrayView() {
  const [data, setData] = useState<LiveXray | null>(null)
  const [observations, setObservations] = useState<LatestObservations | null>(null)
  const [error, setError] = useState(false)
  const [stationError, setStationError] = useState(false)
  const [refreshing, setRefreshing] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState('prediction')
  const [showSupport, setShowSupport] = useState(false)
  const [opacity, setOpacity] = useState(0.88)
  const [focus, setFocus] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [now, setNow] = useState(Date.now)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let controller: AbortController | undefined
    async function load() {
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 20_000)
      const results = await Promise.allSettled([fetchLiveXray(controller.signal), fetchLatestObservations(controller.signal)])
      window.clearTimeout(timeout)
      if (stopped) return
      if (results[0].status === 'fulfilled') { setData(results[0].value); setError(false) } else setError(true)
      if (results[1].status === 'fulfilled') { setObservations(results[1].value); setStationError(false) } else setStationError(true)
      setRefreshing(false)
      setNow(Date.now())
      timer = window.setTimeout(() => void load(), 15_000)
    }
    void load()
    return () => { stopped = true; window.clearTimeout(timer); controller?.abort() }
  }, [attempt])

  useEffect(() => {
    if (!expanded) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false) }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = previous; window.removeEventListener('keydown', onKey) }
  }, [expanded])

  const snapshot = data?.map
  const connected = !!data && !error && !data.refresh.overdue && data.refresh.phase !== 'error'
  const readings = new Map(observations?.readings.map(reading => [reading.parameter_code, reading]))
  const range = snapshot ? `${date(snapshot.acquisition_start)} – ${date(snapshot.acquisition_end)}` : 'Checking recent acquisitions'
  const activeLayer = snapshot?.layers.find(layer => layer.id === selected)
  const min = activeLayer?.display_min ?? 0
  const max = activeLayer?.display_max ?? 4

  return <div className="live-xray">
    <section className="live-intro">
      <div><p className="eyebrow">Satellite intelligence / Green Bay</p><h2>See the bay differently.</h2>
        <p>Recent satellite imagery. A continuous prediction. The river's pulse, live.</p></div>
      <div className="live-connection"><span className={connected ? 'is-connected' : ''}><i />{error ? 'Reconnecting' : connected ? 'Automatic updates on' : data?.refresh.phase === 'error' ? 'Refresh interrupted' : data?.refresh.overdue ? 'Refresh overdue' : 'Connecting data'}</span>
        <button className="btn" disabled={refreshing} onClick={() => { setRefreshing(true); setAttempt(v => v + 1) }}>{refreshing ? 'Syncing…' : '↻ Sync data'}</button></div>
    </section>
    {error && <p className="live-notice" role="alert">Connection interrupted.{snapshot ? ' Showing the last downloaded map with its original acquisition dates.' : ' Retrying automatically.'}</p>}
    {data?.status === 'stale' && <p className="live-notice">The newest usable image is more than three days old. Cloud cover and acquisition timing limit freshness.</p>}
    {snapshot && (data?.refresh.phase === 'error' || data?.refresh.overdue) && <p className="live-notice">Satellite refresh {data.refresh.overdue ? 'is overdue' : 'failed'}. The last completed map remains visible; its imagery dates have not changed.</p>}
    <section className={`live-map-shell ${expanded ? 'is-expanded' : ''}`} aria-label="Green Bay prediction map">
      <div className="live-map-toolbar">
        <div className="live-layer-switch" aria-label="Map layer">{[
          ['prediction', 'Predictions'], ['satellite', 'Satellite'], ['age', 'Image age'],
        ].map(([id, title]) => <button key={id} aria-pressed={selected === id} onClick={() => setSelected(id)}>{title}</button>)}</div>
        <div className="live-map-actions"><button onClick={() => setFocus(v => v + 1)}>⌖ Whole bay</button>
          <button aria-label={expanded ? 'Exit full screen' : 'Expand map'} onClick={() => setExpanded(v => !v)}>{expanded ? '↙ Close' : '⛶ Expand'}</button></div>
      </div>
      <div className="live-map-canvas">
        {snapshot ? <XrayLiveMap snapshot={snapshot} selected={selected} showSupport={showSupport} opacity={opacity} focus={focus} /> :
          <div className="live-map-loading" role="status"><div className="live-orbit" /><h3>{error ? 'Waiting for the API' : data?.refresh.phase === 'error' ? 'Satellite update interrupted' : 'Building the latest view'}</h3><p>{data?.refresh.message ?? 'Connecting satellite predictions and river observations…'}</p><span>The first satellite download can take several minutes.</span></div>}
        <div className="live-map-title"><span>FOXWATCH / XRAY</span><h3>{selected === 'prediction' ? 'The shape of the signal.' : selected === 'satellite' ? 'A view from orbit.' : 'Every pixel has a date.'}</h3>
          <p>{selected === 'prediction' ? 'Predicted chlorophyll fluorescence' : selected === 'satellite' ? 'Sentinel-2 green-band reflectance · water only' : 'Acquisition age at map generation'}</p></div>
        {snapshot && <div className="live-map-stamp"><span>IMAGERY ACQUIRED</span><strong>{range}</strong><small>{snapshot.scenes.length} acquisitions · newest valid pixels first</small></div>}
        {snapshot && <div className="live-map-legend">
          <div className="live-legend-heading"><strong>{selected === 'age' ? 'Image age' : selected === 'satellite' ? 'Satellite reflectance' : 'Predicted fluorescence'}</strong><span>{selected === 'age' ? 'DAYS' : selected === 'satellite' ? 'B03' : 'RFU'}</span></div>
          <div className="xray-colorbar" /><div className="xray-scale-ticks">{[0, .25, .5, .75, 1].map(f => <span key={f}>{(min + f * (max - min)).toFixed(selected === 'satellite' ? 3 : selected === 'age' ? 1 : 0)}</span>)}</div>
          <p>{selected === 'prediction' ? 'Full prediction range. Click the water to inspect a value.' : selected === 'satellite' ? 'Glint-corrected reflectance · full value range. Land and clouds are transparent.' : 'Purple is newer. Yellow is older.'}</p>
        </div>}
      </div>
      <div className="live-map-bottom"><div><span className="live-experimental">{selected === 'satellite' ? 'SATELLITE INPUT' : 'EXPERIMENTAL'}</span><span>{selected === 'satellite' ? 'Green-band reflectance · colorized satellite input, not predicted fluorescence' : '2025-trained model · recent imagery · unvalidated seasonal transfer'}</span></div>
        {selected === 'prediction' && <div className="live-display-options"><label><input type="checkbox" checked={showSupport} onChange={e => setShowSupport(e.target.checked)} />Training limits</label><label>Opacity<input aria-label="Prediction opacity" type="range" min="0.2" max="1" step="0.05" value={opacity} onChange={e => setOpacity(Number(e.target.value))} /></label></div>}
      </div>
    </section>
    <section className="live-river" aria-label="Live river measurements">
      <div className="live-river-heading"><p className="eyebrow">At the mouth of the Fox</p><h3>The river, right now.</h3>
        <p>USGS {observations?.station_id.replace(/^USGS-/, '') ?? 'station'} · {stationError ? 'connection interrupted' : 'refreshes every 15 seconds'}</p><span>Station context · separate from map inputs</span></div>
      {PARAMETERS.map(parameter => {
        const reading = readings.get(parameter.code)
        const delayed = reading && now - Date.parse(reading.observed_at) > (observations?.stale_after_seconds ?? 1800) * 1000
        return <article className="live-river-reading" key={parameter.code}><div><span>{parameter.title}</span><i>{parameter.icon}</i></div>
          <strong>{reading?.value != null ? reading.value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—'} <small>{reading?.unit ?? ''}</small></strong>
          <p>{reading ? date(reading.observed_at, true) : stationError ? 'Station unavailable' : 'Waiting for readings'}{delayed && <b>Delayed</b>}{stationError && reading && <b>Cached</b>}</p></article>
      })}
    </section>
    {snapshot && <section className="live-details"><details><summary>Inside this prediction <span>{snapshot.modeled_area_km2.toLocaleString()} km² of modeled water · {snapshot.resolution_m} m grid</span></summary>
      <div className="live-method"><div><h3>From reflectance to fluorescence</h3><p>{snapshot.note}</p>
        <p>{snapshot.training_bins.toLocaleString()} FLAMe training bins · {snapshot.training_period}. {snapshot.extrapolated_cells.toLocaleString()} cells are beyond 3 km of training locations; {snapshot.outside_feature_range_cells.toLocaleString()} have at least one satellite feature outside the training range.</p>
        <p>Transparent areas have no usable prediction. Each color scale covers the full value range of this snapshot; its limits can change with new data. Click Predictions to inspect a numerical value. A smooth display does not add observations.</p>
        <p>Sharp bands and rectangular patches can occur when the model extrapolates far beyond its training locations. Turn on Training limits to identify unsupported areas; these boundaries are not measured plume edges.</p>
        {snapshot.region && <p>Layers and inspection values are clipped to Green Bay using <a href={snapshot.region.source_url} target="_blank" rel="noreferrer">NWS marine-zone boundaries</a>. This geographic limit does not add training evidence inside the bay.</p>}
        <a href="#/investigate">Explore the original research →</a></div>
        <div><h3>Acquisitions behind the map</h3>{snapshot.scenes.map(scene => <a key={scene.id} href={scene.url} target="_blank" rel="noreferrer"><strong>{date(scene.acquired_at, true)} ↗</strong><span>{scene.id} · {scene.modeled_cells.toLocaleString()} cells</span></a>)}
          <p>Map generated {date(snapshot.generated_at, true)}.<br />Catalog checked {date(data?.refresh.catalog_checked_at ?? snapshot.catalog_checked_at, true)}. Satellite worker checks hourly.</p></div></div>
    </details></section>}
  </div>
}
