import type { HeatmapCell, HeatmapLevel } from '@/components/ConditionHeatmap'
import './DriverRadarVisual.css'

const LEVEL_STOPS: Record<
  HeatmapLevel,
  { fill: string; glow: string; reach: number; pulse: string }
> = {
  good: { fill: '#21918c', glow: '#5ec962', reach: 0.72, pulse: '4s' },
  caution: { fill: '#5ec962', glow: '#fde725', reach: 0.88, pulse: '3s' },
  elevated: { fill: '#fde725', glow: '#f8961e', reach: 1, pulse: '2.2s' },
  missing: { fill: '#3b528b', glow: '#64748b', reach: 0.55, pulse: '5s' },
}

function polar(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

function wedgePath(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  start: number,
  end: number,
) {
  const large = end - start > Math.PI ? 1 : 0
  const p1 = polar(cx, cy, innerR, start)
  const p2 = polar(cx, cy, outerR, start)
  const p3 = polar(cx, cy, outerR, end)
  const p4 = polar(cx, cy, innerR, end)
  return [
    `M ${p1.x} ${p1.y}`,
    `L ${p2.x} ${p2.y}`,
    `A ${outerR} ${outerR} 0 ${large} 1 ${p3.x} ${p3.y}`,
    `L ${p4.x} ${p4.y}`,
    `A ${innerR} ${innerR} 0 ${large} 0 ${p1.x} ${p1.y}`,
    'Z',
  ].join(' ')
}

export function DriverRadarVisual({
  cells,
  score,
  maxScore,
  percentFull,
  classification,
}: {
  cells: HeatmapCell[]
  score?: number
  maxScore?: number
  percentFull?: number
  classification?: string
}) {
  const cx = 220
  const cy = 220
  const innerR = 78
  const outerBase = 168
  const count = Math.max(cells.length, 1)
  const gap = 0.04

  return (
    <div className="driver-radar">
      <svg
        viewBox="0 0 440 440"
        className="driver-radar__svg"
        role="img"
        aria-label="Water condition severity by live readings"
      >
        <defs>
          <radialGradient id="driverRadarBg" cx="50%" cy="45%" r="65%">
            <stop offset="0%" stopColor="#25474e" />
            <stop offset="55%" stopColor="#102630" />
            <stop offset="100%" stopColor="#0a1a20" />
          </radialGradient>
          <filter id="driverGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="driverScanLine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#21918c00" />
            <stop offset="45%" stopColor="#5ec96288" />
            <stop offset="100%" stopColor="#fde72500" />
          </linearGradient>
        </defs>

        <rect width="440" height="440" fill="url(#driverRadarBg)" rx="20" />

        {[0.35, 0.55, 0.75, 1].map((scale) => (
          <circle
            key={scale}
            cx={cx}
            cy={cy}
            r={outerBase * scale}
            fill="none"
            stroke="#ffffff14"
            strokeWidth="1"
            strokeDasharray="4 6"
          />
        ))}

        <ellipse
          cx={cx}
          cy={cy + 8}
          rx={118}
          ry={52}
          fill="none"
          stroke="#c7dd9b33"
          strokeWidth="1.5"
          transform={`rotate(-8 ${cx} ${cy})`}
        />

        {cells.map((cell, index) => {
          const start = (index / count) * Math.PI * 2 - Math.PI / 2 + gap
          const end = ((index + 1) / count) * Math.PI * 2 - Math.PI / 2 - gap
          const style = LEVEL_STOPS[cell.level]
          const outerR = innerR + (outerBase - innerR) * style.reach
          const mid = (start + end) / 2
          const labelPos = polar(cx, cy, outerBase + 22, mid)
          return (
            <g key={cell.id} filter="url(#driverGlow)">
              <path
                d={wedgePath(cx, cy, innerR, outerR, start, end)}
                fill={style.fill}
                fillOpacity={cell.level === 'missing' ? 0.35 : 0.92}
                stroke={style.glow}
                strokeWidth="1.5"
                className="driver-radar__wedge"
                style={{ animationDuration: style.pulse }}
              />
              <circle
                cx={polar(cx, cy, outerR - 8, mid).x}
                cy={polar(cx, cy, outerR - 8, mid).y}
                r={cell.level === 'elevated' ? 5 : 4}
                fill={style.glow}
                className="driver-radar__node"
                style={{ animationDuration: style.pulse }}
              />
              <text
                x={labelPos.x}
                y={labelPos.y}
                textAnchor="middle"
                className="driver-radar__label"
              >
                {cell.label}
              </text>
            </g>
          )
        })}

        <g className="driver-radar__sweep">
          <path
            d={`M ${cx} ${cy} L ${cx} ${cy - outerBase} A ${outerBase} ${outerBase} 0 0 1 ${cx + outerBase * 0.25} ${cy - outerBase * 0.97} Z`}
            fill="url(#driverScanLine)"
            opacity="0.35"
            transform={`rotate(0 ${cx} ${cy})`}
          />
        </g>

        <circle cx={cx} cy={cy} r={innerR - 6} fill="#0b2229ee" stroke="#ffffff22" />
        <text x={cx} y={cy - 8} textAnchor="middle" className="driver-radar__score">
          {percentFull != null ? `${Math.round(percentFull)}%` : '--'}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" className="driver-radar__score-sub">
          {score != null && maxScore != null ? `${score}/${maxScore} pts` : 'BFI'}
        </text>
      </svg>

      <div className="driver-radar__legend">
        <span className="driver-radar__legend-title">Bloom favorability scale</span>
        <div className="xray-colorbar driver-radar__bar" />
        <div className="driver-radar__legend-row">
          <span>Lower</span>
          <span>Higher bloom favorability</span>
        </div>
        {classification ? (
          <p className="driver-radar__class">{classification}</p>
        ) : null}
      </div>
    </div>
  )
}
