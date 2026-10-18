import { useEffect, useMemo, useState } from 'react'
import {
  buildConditionHeatmapCells,
  type HeatmapCell,
} from '@/components/ConditionHeatmap'
import { DriverRadarVisual } from '@/components/DriverRadarVisual'
import type { BfiInsightResponse } from '@/models/bfi'
import type { LatestObservations } from '@/models/observations'
import { fetchBfiInsights } from '@/services/bfiService'
import { fetchLatestObservations } from '@/services/observationsService'
import '../views/XrayView.css'
import './DriversMapView.css'

const LEVEL_LABEL = {
  good: 'Lower bloom favorability',
  caution: 'Moderate',
  elevated: 'Elevated bloom favorability',
  missing: 'No data',
} as const

function DriverDetail({ cell }: { cell: HeatmapCell }) {
  return (
    <li className={`driver-detail driver-detail--${cell.level}`}>
      <div className="driver-detail__head">
        <span className="driver-detail__dot" aria-hidden="true" />
        <strong>{cell.label}</strong>
        <span className="driver-detail__badge">{LEVEL_LABEL[cell.level]}</span>
      </div>
      {cell.valueText ? <p className="driver-detail__value">{cell.valueText}</p> : null}
      <p className="driver-detail__note">{cell.detail}</p>
    </li>
  )
}

export function DriversMapView() {
  const [observations, setObservations] = useState<LatestObservations | null>(null)
  const [bfi, setBfi] = useState<BfiInsightResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let controller: AbortController | undefined

    async function load() {
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 20_000)
      try {
        const [obs, bloom] = await Promise.allSettled([
          fetchLatestObservations(controller.signal),
          fetchBfiInsights({ use_live_data: true, use_gemini: false }, controller.signal),
        ])
        if (stopped) return
        if (obs.status === 'fulfilled') {
          setObservations(obs.value)
          setError(null)
        } else {
          setError('Could not load station readings.')
        }
        if (bloom.status === 'fulfilled') {
          setBfi(bloom.value)
        } else {
          setBfi(null)
          setError((prev) => prev ?? 'Live bloom driver scores need Tiger Data and the API.')
        }
      } finally {
        window.clearTimeout(timeout)
        setLoading(false)
        if (!stopped) timer = window.setTimeout(() => void load(), 15_000)
      }
    }

    void load()
    return () => {
      stopped = true
      controller?.abort()
      window.clearTimeout(timer)
    }
  }, [])

  const cells = useMemo(() => {
    const byCode = new Map(observations?.readings.map((r) => [r.parameter_code, r]))
    return buildConditionHeatmapCells(bfi?.bfi.factors, byCode)
  }, [bfi?.bfi.factors, observations?.readings])

  const fullMax = bfi?.bfi.full_max_score ?? 12
  const pctFull =
    bfi?.bfi.favorability_percent_full ??
    (bfi?.bfi.score != null ? Math.round((bfi.bfi.score / fullMax) * 100) : undefined)

  return (
    <div className="driver-scan">
      <p className="driver-scan__lede">
        Live bloom-driver scan for the Fox River mouth. Wedge length and color follow the same
        viridis-style scale as X-Ray the Bay: cool tones mean lower bloom favorability, bright
        yellow means more bloom-favorable conditions. Not a bloom forecast.
      </p>

      {error ? (
        <p className="live-notice" role="alert">
          {error}
        </p>
      ) : null}

      <section className="driver-scan__stage" aria-label="Bloom driver radar">
        {loading && !bfi ? (
          <div className="live-map-loading driver-scan__loading" role="status">
            <div className="live-orbit" />
            <h3>Scanning live drivers</h3>
            <p>Pulling USGS, rainfall, and BFI inputs...</p>
          </div>
        ) : (
          <div className="driver-scan__layout">
            <DriverRadarVisual
              cells={cells}
              score={bfi?.bfi.score}
              maxScore={fullMax}
              percentFull={pctFull}
              classification={bfi?.bfi.classification}
            />
            <aside className="driver-scan__panel">
              <h2 className="driver-scan__panel-title">Driver readout</h2>
              <ul className="driver-detail-list">
                {cells.map((cell) => (
                  <DriverDetail key={cell.id} cell={cell} />
                ))}
              </ul>
            </aside>
          </div>
        )}
      </section>
    </div>
  )
}
