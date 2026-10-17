import { useId, useState } from 'react'
import { useOpenEvidence } from '../components/EvidenceContext'
import { FixtureBadge } from '../components/FixtureBadge'
import { ObservationChart } from '../components/ObservationChart'
import { ProxyMap } from '../components/ProxyMap'
import { ScenarioPanel } from '../components/ScenarioPanel'
import { SceneTimeline } from '../components/SceneTimeline'
import { useReplayData } from '../features/replay/ReplayDataContext'
import { formatDay, proxyColor } from '../lib/format'

function rainBefore(
  observations: { metric: string; observation_date: string | null; value: number | null }[],
  iso: string,
  days: number,
) {
  const t = Date.parse(iso)
  return observations.filter((o) => {
    if (o.metric !== 'precipitation' || o.value === null) return false
    const d = Date.parse(`${o.observation_date}T12:00:00Z`)
    return d <= t && d > t - days * 86_400_000
  }).reduce((sum, o) => sum + (o.value ?? 0), 0)
}

export function ReplayView() {
  const { scenes, observations } = useReplayData()
  const [index, setIndex] = useState(2)
  const [showOverlay, setShowOverlay] = useState(true)
  const [opacity, setOpacity] = useState(0.85)
  const opacityId = useId()
  const openEvidence = useOpenEvidence()

  const scene = scenes[index] ?? scenes[0]
  const prevClear = scenes.slice(0, index)
    .reverse()
    .find((s) => s.quality_flag !== 'cloud_limited')
  const delta = prevClear ? scene.proxy_mean - prevClear.proxy_mean : null
  const discharge = observations.find(
    (o) =>
      o.metric === 'discharge' &&
      o.observation_date === scene.acquired_at_utc.slice(0, 10),
  )
  const cloudy = scene.quality_flag === 'cloud_limited'

  return (
    <div className="replay">
      <section className="replay__map card card--flush" aria-labelledby="map-title">
        <div className="map-wrap">
          <h2 id="map-title" className="sr-only">
            Satellite proxy map for {formatDay(scene.acquired_at_utc)}
          </h2>
          <ProxyMap scene={scene} showOverlay={showOverlay} opacity={opacity} />

          <div className="map-hud map-hud--top">
            <div className="hud-card">
              <p className="hud-card__eyebrow">Sentinel-2 L2A</p>
              <p className="hud-card__date">
                {new Date(scene.acquired_at_utc).toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                  timeZone: 'UTC',
                })}
              </p>
              {cloudy ? (
                <span className="chip chip--warn">
                  {scene.cloud_cover_pct}% cloud · interpret with care
                </span>
              ) : (
                <span className="chip chip--ok">
                  {scene.cloud_cover_pct}% cloud · usable
                </span>
              )}
            </div>
          </div>

          <div className="map-hud map-hud--bottom">
            <div className="hud-card hud-card--legend">
              <p className="hud-card__eyebrow">{scene.proxy_name} proxy · dimensionless</p>
              <div
                className="legend-ramp"
                style={{
                  background: `linear-gradient(90deg, ${[0, 0.33, 0.66, 1]
                    .map((t) => proxyColor(t))
                    .join(', ')})`,
                }}
                aria-hidden="true"
              />
              <div className="legend-labels" aria-hidden="true">
                <span>Lower</span>
                <span>Higher</span>
              </div>
              <div className="hud-controls">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={showOverlay}
                    onChange={(e) => setShowOverlay(e.target.checked)}
                  />
                  <span className="toggle__track" aria-hidden="true" />
                  Proxy layer
                </label>
                <label htmlFor={opacityId} className="sr-only">
                  Proxy layer opacity
                </label>
                <input
                  id={opacityId}
                  type="range"
                  min={0.2}
                  max={1}
                  step={0.05}
                  value={opacity}
                  disabled={!showOverlay}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                />
              </div>
              <p className="hud-card__note">Illustrative overlay · demo fixture</p>
            </div>
          </div>
        </div>

        <SceneTimeline scenes={scenes} index={index} onChange={setIndex} />
      </section>

      <aside className="replay__side" aria-label="Selected scene details">
        <section className="card scene-card">
          <header className="card__header">
            <div>
              <p className="eyebrow">Selected scene</p>
              <h2 className="card__title">{formatDay(scene.acquired_at_utc)}, 2020</h2>
            </div>
            <FixtureBadge />
          </header>

          <div className="stats">
            <div className="stat stat--algae">
              <span className="stat__label">Proxy mean</span>
              <span className="stat__value">{scene.proxy_mean.toFixed(2)}</span>
              <span className="stat__foot">
                {delta === null
                  ? 'first clear scene'
                  : `${delta >= 0 ? '▲' : '▼'} ${Math.abs(delta).toFixed(2)} vs ${formatDay(prevClear!.acquired_at_utc)}`}
              </span>
            </div>
            <div className="stat stat--water">
              <span className="stat__label">River discharge</span>
              <span className="stat__value">
                {discharge?.value != null
                  ? `${(discharge.value / 1000).toFixed(1)}k`
                  : '—'}
              </span>
              <span className="stat__foot">
                {discharge?.value != null ? 'ft³/s · daily mean' : 'not reported this day'}
              </span>
            </div>
            <div className="stat stat--rain">
              <span className="stat__label">Rain, prior 5 days</span>
              <span className="stat__value">
                {rainBefore(observations, scene.acquired_at_utc, 5).toFixed(1)}
              </span>
              <span className="stat__foot">mm · NOAA daily totals</span>
            </div>
            <div className="stat stat--fox">
              <span className="stat__label">Cloud cover</span>
              <span className="stat__value">{scene.cloud_cover_pct}%</span>
              <span className="stat__foot">{cloudy ? 'cloud limited' : 'usable scene'}</span>
            </div>
          </div>

          <div className="scene-card__actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => openEvidence(scene.evidence_id)}
            >
              Open scene evidence
            </button>
            <a className="btn btn--primary" href="#/review">
              Review this scene →
            </a>
          </div>
        </section>

        <ScenarioPanel scene={scene} />
      </aside>

      <div className="replay__chart">
        <ObservationChart scene={scene} />
      </div>
    </div>
  )
}
