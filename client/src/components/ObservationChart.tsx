import type { Scene } from '../data/types/replay'
import { useReplayData } from '../features/replay/ReplayDataContext'
import { formatDay } from '../lib/format'
import { useOpenEvidence } from './EvidenceContext'
import { FixtureBadge } from './FixtureBadge'

const W = 760
const H = 240
const PAD = { top: 18, right: 52, bottom: 30, left: 56 }
const innerW = W - PAD.left - PAD.right
const innerH = H - PAD.top - PAD.bottom

export function ObservationChart({ scene }: { scene: Scene }) {
  const openEvidence = useOpenEvidence()
  const { event, observations } = useReplayData()
  const discharge = observations.filter((o) => o.metric === 'discharge')
  const rain = observations.filter((o) => o.metric === 'precipitation')

  const start = Date.parse(`${event.start_date}T00:00:00Z`)
  const end = Date.parse(`${event.end_date}T23:59:59Z`)
  const x = (iso: string) =>
    PAD.left + ((Date.parse(iso) - start) / (end - start)) * innerW

  const qMax = Math.max(
    1000,
    ...discharge.map((o) => o.value ?? 0),
    1,
  )
  const rMax = Math.max(1, ...rain.map((o) => o.value ?? 0))
  const yQ = (v: number) => PAD.top + innerH - (v / qMax) * innerH
  const yR = (v: number) => (v / rMax) * innerH * 0.55

  const segments: string[] = []
  let current: string[] = []
  for (const o of discharge) {
    if (!o.observation_date) continue
    if (o.value === null) {
      if (current.length) segments.push(current.join(' '))
      current = []
      continue
    }
    const px = x(`${o.observation_date}T12:00:00Z`)
    current.push(`${current.length ? 'L' : 'M'}${px.toFixed(1)},${yQ(o.value).toFixed(1)}`)
  }
  if (current.length) segments.push(current.join(' '))

  const barW = (innerW / 14) * 0.5
  const sceneX = x(scene.acquired_at_utc)

  return (
    <figure className="card chart-card">
      <figcaption className="card__header">
        <div>
          <h2 className="card__title">River &amp; rain context</h2>
          <p className="card__sub">
            Daily values at native cadence. Gaps mean no reported value, not
            zero.
          </p>
        </div>
        <FixtureBadge />
      </figcaption>

      <div className="chart-legend" aria-hidden="true">
        <span>
          <i className="swatch swatch--line" /> Discharge (ft³/s)
        </span>
        {rain.length > 0 ? (
          <span>
            <i className="swatch swatch--bar" /> Precipitation (mm)
          </span>
        ) : null}
        <span>
          <i className="swatch swatch--gap" /> No data
        </span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart"
        role="img"
        aria-labelledby="chart-title chart-desc"
      >
        <title id="chart-title">
          River context, {event.start_date} – {event.end_date}
        </title>
        <desc id="chart-desc">
          Daily discharge with gaps where no value was reported. A data table
          follows this chart.
        </desc>
        <defs>
          <linearGradient id="q-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--water)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--water)" stopOpacity="0" />
          </linearGradient>
          <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--muted)" strokeWidth="2" strokeOpacity="0.35" />
          </pattern>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const v = Math.round(qMax * t)
          return (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={yQ(v)}
                y2={yQ(v)}
                className="chart__grid"
              />
              <text x={PAD.left - 8} y={yQ(v) + 4} className="chart__axis" textAnchor="end">
                {v === 0 ? '0' : v >= 1000 ? `${Math.round(v / 1000)}k` : v}
              </text>
            </g>
          )
        })}

        {rain.map((r) => {
          if (!r.observation_date) return null
          const cx = x(`${r.observation_date}T12:00:00Z`)
          if (r.value === null) {
            return (
              <rect
                key={r.evidence_id}
                x={cx - barW / 2}
                y={PAD.top}
                width={barW}
                height={innerH}
                fill="url(#hatch)"
              />
            )
          }
          const h = yR(r.value)
          return (
            <rect
              key={r.evidence_id}
              x={cx - barW / 2}
              y={PAD.top}
              width={barW}
              height={Math.max(h, r.value > 0 ? 2 : 0)}
              rx={3}
              className="chart__rain"
            >
              <title>{`${r.observation_date}: ${r.value} mm`}</title>
            </rect>
          )
        })}

        {discharge.map((o) => {
          if (o.value !== null || !o.observation_date) return null
          const cx = x(`${o.observation_date}T12:00:00Z`)
          return (
            <rect
              key={o.evidence_id}
              x={cx - barW / 2}
              y={PAD.top}
              width={barW}
              height={innerH}
              fill="url(#hatch)"
            />
          )
        })}

        {segments.map((d) => (
          <path key={d} d={d} className="chart__line" />
        ))}

        <line
          x1={sceneX}
          x2={sceneX}
          y1={PAD.top - 6}
          y2={PAD.top + innerH}
          className="chart__marker"
        />
        <text x={sceneX} y={PAD.top - 8} textAnchor="middle" className="chart__marker-label">
          Scene · {formatDay(scene.acquired_at_utc)}
        </text>

        {discharge.map((o) =>
          o.value === null || !o.observation_date ? null : (
            <circle
              key={o.evidence_id}
              cx={x(`${o.observation_date}T12:00:00Z`)}
              cy={yQ(o.value)}
              r={5}
              className="chart__point"
              tabIndex={0}
              role="button"
              aria-label={`Discharge ${o.observation_date}: ${o.value.toLocaleString()} ft³/s. Open evidence.`}
              onClick={() => openEvidence(o.evidence_id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  openEvidence(o.evidence_id)
                }
              }}
            />
          ),
        )}

        {discharge.map((o, i) =>
          i % 2 === 0 && o.observation_date ? (
            <text
              key={`t-${o.observation_date}`}
              x={x(`${o.observation_date}T12:00:00Z`)}
              y={H - 8}
              textAnchor="middle"
              className="chart__axis"
            >
              {formatDay(`${o.observation_date}T12:00:00Z`)}
            </text>
          ) : null,
        )}
      </svg>

      <details className="chart-table">
        <summary>View as table</summary>
        <table>
          <caption className="sr-only">Daily discharge and precipitation</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Discharge (ft³/s)</th>
              <th scope="col">Precipitation (mm)</th>
            </tr>
          </thead>
          <tbody>
            {discharge.map((o, i) => (
              <tr key={o.evidence_id}>
                <th scope="row">{o.observation_date ?? '—'}</th>
                <td>{o.value?.toLocaleString() ?? 'No data'}</td>
                <td>{rain[i]?.value ?? 'No data'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
