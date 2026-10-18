import { useEffect, useRef, useState } from 'react'
import { XrayLiveMap } from '@/components/XrayLiveMap'
import { XrayExplanation } from '@/components/XrayExplanation'
import type { ExplanationSelection, LiveXray } from '@/models/xrayLive'
import type { LatestObservations } from '@/models/observations'
import { fetchLiveXray } from '@/services/xrayService'
import { fetchLatestObservations } from '@/services/observationsService'
import './XrayView.css'
import './XrayLiveView.css'

const date = (value: string, includeTime = false) =>
  new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    ...(includeTime ? { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' as const } : {}),
  })

const PARAMETERS = [
  { code: '00010', title: 'Water temperature' },
  { code: '00060', title: 'River discharge' },
  { code: '00300', title: 'Dissolved oxygen' },
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
  const [explanation, setExplanation] = useState<ExplanationSelection>()
  const mapShellRef = useRef<HTMLElement>(null)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let controller: AbortController | undefined
    async function load() {
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 20_000)
      const results = await Promise.allSettled([
        fetchLiveXray(controller.signal),
        fetchLatestObservations(controller.signal),
      ])
      window.clearTimeout(timeout)
      if (stopped) return
      if (results[0].status === 'fulfilled') {
        setData(results[0].value)
        setError(false)
      } else setError(true)
      if (results[1].status === 'fulfilled') {
        setObservations(results[1].value)
        setStationError(false)
      } else setStationError(true)
      setRefreshing(false)
      setNow(Date.now())
      timer = window.setTimeout(() => void load(), 15_000)
    }
    void load()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      controller?.abort()
    }
  }, [attempt])

  useEffect(() => {
    if (!expanded) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false)
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
    }
  }, [expanded])

  const snapshot = data?.map
  const connected = !!data && !error && !data.refresh.overdue && data.refresh.phase !== 'error'

  const readings = new Map(observations?.readings.map((reading) => [reading.parameter_code, reading]))
  const range = snapshot
    ? `${date(snapshot.acquisition_start)} to ${date(snapshot.acquisition_end)}`
    : 'Checking recent acquisitions'
  const activeLayer = snapshot?.layers.find((layer) => layer.id === selected)
  const min = activeLayer?.display_min ?? 0
  const max = activeLayer?.display_max ?? 4

  return (
    <div className="live-xray live-xray--tight">
      <details className="live-about" open>
        <summary>About this map</summary>
        <div className="live-about__body">
          <div className="live-intro__about">
            <p>
              A live map of Green Bay from recent Sentinel-2 imagery. Colors show where a satellite model
              estimates chlorophyll fluorescence (RFU). That is a pigment signal, not a confirmed harmful bloom.
            </p>
            <p className="muted">
              Tap open water on the <strong>Predictions</strong> layer for a reading and explanation. Fox River
              USGS measurements below add river context. Experimental. Not a health or recreation advisory.
            </p>
            <a href="#/investigate">How we validated the model</a>
          </div>
          <div className="live-connection live-connection--row live-about__sync">
            <span className={connected ? 'is-connected' : ''}>
              <i />
              {error
                ? 'Reconnecting'
                : connected
                  ? 'Auto-updating'
                  : data?.refresh.phase === 'error'
                    ? 'Refresh interrupted'
                    : data?.refresh.overdue
                      ? 'Refresh overdue'
                      : 'Connecting data'}
            </span>
            <button
              type="button"
              className="btn btn--compact"
              disabled={refreshing}
              onClick={() => {
                setRefreshing(true)
                setAttempt((v) => v + 1)
              }}
            >
              {refreshing ? 'Syncing...' : 'Refresh'}
            </button>
          </div>
        </div>
      </details>
      {error && !snapshot && (
        <p className="live-notice" role="alert">
          Could not reach the FoxWatch API for live satellite layers. Start the API on port 8000 (
          <code>cd api && uv run python main.py</code>) and press Refresh.
        </p>
      )}
      {error && snapshot && (
        <p className="live-notice" role="alert">
          Connection interrupted. Showing the last available map.
        </p>
      )}
      {data?.status === 'stale' && <p className="live-notice">Latest imagery is over three days old.</p>}
      {snapshot && (data?.refresh.phase === 'error' || data?.refresh.overdue) && (
        <p className="live-notice">
          Satellite refresh {data.refresh.overdue ? 'is overdue' : 'failed'}. Showing the last available map.
        </p>
      )}
      <section
        ref={mapShellRef}
        className={`live-map-shell ${expanded ? 'is-expanded' : ''}`}
        aria-label="Green Bay prediction map"
      >
        <div className="live-map-toolbar">
          <div className="live-layer-switch" aria-label="Map layer">
            {[
              ['prediction', 'Predictions'],
              ['satellite', 'Satellite'],
              ['age', 'Image age'],
            ].map(([id, title]) => (
              <button
                key={id}
                type="button"
                aria-pressed={selected === id}
                onClick={() => setSelected(id)}
              >
                {title}
              </button>
            ))}
          </div>
          <div className="live-map-actions">
            <button type="button" onClick={() => setFocus((v) => v + 1)}>
              Whole bay
            </button>
            <button
              type="button"
              aria-label={expanded ? 'Exit full screen' : 'Expand map'}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? 'Close' : 'Expand'}
            </button>
          </div>
        </div>
        <div className="live-map-canvas">
          {snapshot ? (
            <XrayLiveMap
              snapshot={snapshot}
              selected={selected}
              showSupport={showSupport}
              opacity={opacity}
              focus={focus}
              onExplain={setExplanation}
            />
          ) : (
            <div className="live-map-loading" role="status">
              <div className="live-orbit" />
              <h3>
                {error
                  ? 'Map unavailable'
                  : data?.refresh.phase === 'error'
                    ? 'Satellite update interrupted'
                    : 'Loading satellite map'}
              </h3>
              <p>Checking available imagery...</p>
            </div>
          )}
          <div className="live-map-title">
            <h3>
              {selected === 'prediction'
                ? 'Predicted fluorescence'
                : selected === 'satellite'
                  ? 'Satellite reflectance'
                  : 'Image age'}
            </h3>
            <p>
              {selected === 'prediction'
                ? 'Chlorophyll fluorescence, RFU'
                : selected === 'satellite'
                  ? 'Sentinel-2, green band'
                  : 'Days at map generation'}
            </p>
          </div>
          {snapshot && (
            <div className="live-map-stamp">
              <span>IMAGERY ACQUIRED</span>
              <strong>{range}</strong>
              <small>{snapshot.scenes.length} acquisitions</small>
            </div>
          )}
          {snapshot && (
            <div className="live-map-legend">
              <div className="live-legend-heading">
                <strong>
                  {selected === 'age'
                    ? 'Image age'
                    : selected === 'satellite'
                      ? 'Satellite reflectance'
                      : 'Predicted fluorescence'}
                </strong>
                <span>{selected === 'age' ? 'DAYS' : selected === 'satellite' ? 'B03' : 'RFU'}</span>
              </div>
              <div className="xray-colorbar" />
              <div className="xray-scale-ticks">
                {[0, 0.25, 0.5, 0.75, 1].map((f) => (
                  <span key={f}>
                    {(min + f * (max - min)).toFixed(
                      selected === 'satellite' ? 3 : selected === 'age' ? 1 : 0,
                    )}
                  </span>
                ))}
              </div>
              <p>
                {selected === 'prediction'
                  ? 'Click water to inspect.'
                  : selected === 'satellite'
                    ? 'Land and cloud gaps are uncolored.'
                    : 'Purple is newer. Yellow is older.'}
              </p>
            </div>
          )}
          {snapshot && explanation && (
            <XrayExplanation
              key={`${explanation.runId}:${explanation.lat}:${explanation.lon}`}
              selection={explanation}
              currentRunId={snapshot.run_id}
              onClose={() => setExplanation(undefined)}
            />
          )}
        </div>
        <div className="live-map-bottom">
          <div>
            <span className="live-experimental">
              {selected === 'satellite' ? 'SATELLITE INPUT' : 'EXPERIMENTAL'}
            </span>
            <span>
              {selected === 'satellite'
                ? 'Colorized reflectance'
                : '2025-trained model. Current-season accuracy remains unverified.'}
            </span>
          </div>
          {selected === 'prediction' && (
            <div className="live-display-options">
              <label>
                <input
                  type="checkbox"
                  checked={showSupport}
                  onChange={(e) => setShowSupport(e.target.checked)}
                />
                Training limits
              </label>
              <label>
                Opacity
                <input
                  aria-label="Prediction opacity"
                  type="range"
                  min="0.2"
                  max="1"
                  step="0.05"
                  value={opacity}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                />
              </label>
            </div>
          )}
        </div>
      </section>
      <section className="live-river" aria-label="Live river measurements">
        <div className="live-river-heading">
          <h3>Fox River observations</h3>
          <p>
            USGS {observations?.station_id.replace(/^USGS-/, '') ?? 'station'},{' '}
            {stationError ? 'connection interrupted' : 'latest readings'}
          </p>
          <a href="#/current">All station readings</a>
        </div>
        {PARAMETERS.map((parameter) => {
          const reading = readings.get(parameter.code)
          const delayed =
            reading &&
            now - Date.parse(reading.observed_at) > (observations?.stale_after_seconds ?? 1800) * 1000
          return (
            <article className="live-river-reading" key={parameter.code}>
              <div>
                <span>{parameter.title}</span>
              </div>
              <strong>
                {reading?.value != null
                  ? reading.value.toLocaleString(undefined, { maximumFractionDigits: 1 })
                  : '--'}{' '}
                <small>{reading?.unit ?? ''}</small>
              </strong>
              <p>
                {reading
                  ? date(reading.observed_at, true)
                  : stationError
                    ? 'Station unavailable'
                    : 'Waiting for readings'}
                {delayed && <b>Delayed</b>}
                {stationError && reading && <b>Cached</b>}
              </p>
            </article>
          )
        })}
      </section>
      {snapshot && (
        <section className="live-details">
          <details>
            <summary>
              Data and methods{' '}
              <span>
                {snapshot.modeled_area_km2.toLocaleString()} sq km of modeled water, {snapshot.resolution_m} m
                grid
              </span>
            </summary>
            <div className="live-method">
              <div>
                <h3>Model</h3>
                <p>
                  Location plus satellite random forest. RFU estimates fluorescence, not bloom probability.
                  River measurements are separate context.
                </p>
                <p>
                  {snapshot.training_bins.toLocaleString()} FLAMe training bins, {snapshot.training_period}.{' '}
                  {snapshot.extrapolated_cells.toLocaleString()} cells are beyond 3 km of training locations.{' '}
                  {snapshot.outside_feature_range_cells.toLocaleString()} have at least one satellite feature
                  outside the training range.
                </p>
                <p>
                  Uncolored areas have no usable prediction. Scales adjust to each snapshot. Smoothing adds no
                  measurements.
                </p>
                <p>
                  Sharp edges may be model artifacts. Training limits marks areas beyond spatial or spectral
                  training ranges.
                </p>
                {snapshot.region && (
                  <p>
                    Coverage follows{' '}
                    <a href={snapshot.region.source_url} target="_blank" rel="noreferrer">
                      NWS marine-zone boundaries
                    </a>
                    . This boundary does not establish model accuracy.
                  </p>
                )}
                <a href="#/investigate">Model validation</a>
              </div>
              <div>
                <h3>Satellite acquisitions</h3>
                {snapshot.scenes.map((scene) => (
                  <a key={scene.id} href={scene.url} target="_blank" rel="noreferrer">
                    <strong>{date(scene.acquired_at, true)}</strong>
                    <span>
                      {scene.id}, {scene.modeled_cells.toLocaleString()} cells
                    </span>
                  </a>
                ))}
                <p>
                  Map generated {date(snapshot.generated_at, true)}.
                  <br />
                  Catalog checked{' '}
                  {date(data?.refresh.catalog_checked_at ?? snapshot.catalog_checked_at, true)}.
                </p>
              </div>
            </div>
          </details>
        </section>
      )}
    </div>
  )
}
