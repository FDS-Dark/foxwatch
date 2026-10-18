import type { SatelliteModel, XraySegment } from '@/models/xray'

export function XrayProfile({ segment, satelliteModel }: { segment: XraySegment; satelliteModel: SatelliteModel }) {
  const points = segment.points
  const showSatellite = segment.stage === 'satellite' || segment.stage === 'reveal'
  const reveal = segment.stage === 'reveal'
  const series = [
    { label: 'Location-only RF', color: '#2a7fa3', values: points.map(p => p.predictions?.rf_xy) },
    ...(showSatellite ? [{ label: satelliteModel === 'gp_resid' ? 'Satellite trend + GP' : 'Location + satellite RF', color: '#b9461f', values: points.map(p => p.predictions?.[satelliteModel]) }] : []),
    ...(reveal ? [{ label: 'Withheld measurements', color: '#132f35', values: points.map(p => p.value) }] : []),
  ]
  const maxY = Math.max(2, ...series.flatMap(s => s.values.filter((v): v is number => v !== undefined))) * 1.1
  const maxX = Math.max(1, ...points.map(p => p.distance_km))
  const x = (value: number) => 52 + value / maxX * 684
  const y = (value: number) => 190 - value / maxY * 160
  return (
    <section className="card xray-profile" aria-label="Withheld segment comparison chart">
      <div className="xray-row"><h3>Along the hidden track</h3><span className="muted">Chlorophyll fluorescence · RFU</span></div>
      {segment.stage === 'hidden' ? <p className="xray-empty">The {segment.matched_count} comparison measurements are hidden. Show a reconstruction to begin.</p> : <>
        <svg viewBox="0 0 760 230" role="img" aria-label={`Segment ${segment.id} prediction profile${reveal ? ' compared with withheld measurements' : '; ground truth remains hidden'}`}>
          {[0, 0.5, 1].map(fraction => <g key={fraction}>
            <line x1={52} y1={y(maxY * fraction)} x2={736} y2={y(maxY * fraction)} stroke="#e3ddd0" />
            <text x={42} y={y(maxY * fraction) + 4} textAnchor="end">{(maxY * fraction).toFixed(1)}</text>
          </g>)}
          {series.map(s => <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={s.label === 'Withheld measurements' ? 3 : 2.5}
            points={s.values.map((value, i) => value === undefined ? '' : `${x(points[i].distance_km)},${y(value)}`).join(' ')} />)}
          <text x={52} y={212}>0 km</text><text x={736} y={212} textAnchor="end">{maxX.toFixed(1)} km along segment</text>
        </svg>
        <div className="xray-legend">{series.map(s => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      </>}
      <p className="muted">Only satellite-matched bins are compared ({segment.matched_count} of {segment.total_count}). Lines connect sampled bins; they are not additional measurements.</p>
    </section>
  )
}
