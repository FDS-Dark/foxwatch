const MAX_POINTS = 2

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
  maxScore,
  favorabilityPercent,
  factors,
}: {
  score: number
  maxScore: number
  favorabilityPercent?: number
  factors?: Array<Record<string, unknown>>
}) {
  const pct =
    favorabilityPercent ??
    (maxScore > 0 ? Math.round((score / maxScore) * 100) : 0)
  const clamped = Math.min(100, Math.max(0, pct))

  const rows =
    factors?.map((row) => {
      const points = Number(row.points ?? 0)
      const status = String(row.status ?? 'neutral')
      const label = shortFactorLabel(String(row.factor ?? 'Factor'))
      return { label, points, status, width: (points / MAX_POINTS) * 100 }
    }) ?? []

  const radius = 52
  const stroke = 10
  const circumference = 2 * Math.PI * radius
  const dash = (clamped / 100) * circumference

  return (
    <div className="bfi-chart">
      <h3 className="card__title">Score breakdown</h3>
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
              {score}/{maxScore} pts
            </text>
          </svg>
        </div>
        <div className="bfi-chart__bars" role="img" aria-label={`Favorability ${clamped} percent`}>
          {rows.length === 0 ? (
            <p className="muted bfi-chart__empty">Factor details unavailable.</p>
          ) : (
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
                  <span className="bfi-chart__bar-pts">{row.points}/{MAX_POINTS}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
