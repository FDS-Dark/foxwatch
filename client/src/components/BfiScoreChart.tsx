const MAX_POINTS = 2
const FULL_SCORE = 12

const ALL_DRIVERS = [
  'Temperature',
  'Phosphorus',
  'Nitrogen',
  'Streamflow',
  'Rainfall',
  'Sunlight',
] as const

const STATUS_FILL: Record<string, string> = {
  favorable: 'var(--algae-bright, #3d9b6a)',
  neutral: 'var(--bay-mid, #6ba3b8)',
  unfavorable: 'var(--fox-soft, #c4a484)',
  missing: 'var(--border, #d8e0e4)',
}

function shortFactorLabel(factor: string): string {
  const map: Record<string, string> = {
    'Water temperature': 'Temperature',
    'Orthophosphate, water, filtered': 'Phosphorus',
    'Nitrate plus nitrite, water, filtered': 'Nitrogen',
    Discharge: 'Streamflow',
    'Precipitation (7-day total)': 'Rainfall',
    'Solar radiation': 'Sunlight',
  }
  return map[factor] ?? factor.replace(/,.*/, '').trim()
}

export function BfiScoreChart({
  score,
  favorabilityPercentFull,
  driversReporting,
  factors,
  compact = false,
}: {
  score: number
  favorabilityPercentFull?: number
  driversReporting?: number
  factors?: Array<Record<string, unknown>>
  compact?: boolean
}) {
  const pct =
    favorabilityPercentFull ??
    Math.round((score / FULL_SCORE) * 100)
  const clamped = Math.min(100, Math.max(0, pct))

  const byLabel = new Map<string, { points: number; status: string }>()
  for (const row of factors ?? []) {
    const label = shortFactorLabel(String(row.factor ?? 'Factor'))
    byLabel.set(label, {
      points: Number(row.points ?? 0),
      status: String(row.status ?? 'neutral'),
    })
  }
  const rows = ALL_DRIVERS.map((label) => {
    const hit = byLabel.get(label)
    if (hit) {
      return { label, points: hit.points, status: hit.status, width: (hit.points / MAX_POINTS) * 100 }
    }
    return { label, points: 0, status: 'missing', width: 0 }
  })

  const radius = 52
  const stroke = 10
  const circumference = 2 * Math.PI * radius
  const dash = (clamped / 100) * circumference

  return (
    <div className={`bfi-chart${compact ? ' bfi-chart--compact' : ''}`}>
      {compact ? (
        <p className="sr-only">Score breakdown</p>
      ) : (
        <h3 className="card__title">Score breakdown</h3>
      )}
      <div className="bfi-chart__body">
        <div className="bfi-chart__gauge" aria-hidden="true">
          <svg viewBox="0 0 120 120" className="bfi-chart__svg">
            <circle
              cx="60"
              cy="60"
              r={radius}
              fill="none"
              stroke="var(--fox-soft, #f5ebe3)"
              strokeWidth={stroke}
            />
            <circle
              cx="60"
              cy="60"
              r={radius}
              fill="none"
              stroke="url(#bfiGaugeGrad)"
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${circumference - dash}`}
              transform="rotate(-90 60 60)"
            />
            <defs>
              <linearGradient id="bfiGaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="var(--algae, #2d7a4f)" />
                <stop offset="100%" stopColor="var(--algae-bright, #3d9b6a)" />
              </linearGradient>
            </defs>
            <text x="60" y="56" textAnchor="middle" className="bfi-chart__gauge-pct">
              {Math.round(clamped)}%
            </text>
            <text x="60" y="72" textAnchor="middle" className="bfi-chart__gauge-sub">
              {score}/{FULL_SCORE} pts
            </text>
          </svg>
        </div>
        <div className="bfi-chart__bars" role="img" aria-label={`${score} of ${FULL_SCORE} points, ${clamped} percent of full score`}>
          <ul className="bfi-chart__bar-list">
            {rows.map((row) => (
              <li key={row.label} className="bfi-chart__bar-row">
                <span className="bfi-chart__bar-label">{row.label}</span>
                <span className="bfi-chart__bar-track">
                  <span
                    className="bfi-chart__bar-fill"
                    style={{
                      width: `${row.width}%`,
                      background: STATUS_FILL[row.status] ?? STATUS_FILL.neutral,
                    }}
                  />
                </span>
                <span className="bfi-chart__bar-pts">
                  {row.status === 'missing' ? '—' : `${row.points}/${MAX_POINTS}`}
                </span>
              </li>
            ))}
          </ul>
          {driversReporting != null && driversReporting < ALL_DRIVERS.length ? (
            <p className="muted bfi-chart__coverage">
              {driversReporting} of {ALL_DRIVERS.length} drivers in today&apos;s feed. Missing drivers count as 0 toward the 12-point total.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
