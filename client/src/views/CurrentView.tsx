import { useEffect, useState } from 'react'
import { BloomPredictionCard } from '../components/BloomPredictionCard'
import type { BloomPrediction } from '@/models/prediction'
import type { LatestObservations } from '@/models/observations'
import { fetchLatestObservations } from '@/services/observationsService'
import { fetchLatestPrediction } from '@/services/predictionsService'
import { isObservationStale } from '@/lib/observationFreshness'
import './CurrentView.css'

const PARAMETERS: Record<string, string> = {
  '32319': 'Phycocyanin fluorescence',
  '32316': 'Chlorophyll fluorescence',
  '00300': 'Dissolved oxygen',
  '00400': 'pH',
  '00010': 'Water temperature',
  '00671': 'Dissolved orthophosphate',
  '00631': 'Nitrate + nitrite',
  '00608': 'Dissolved ammonia',
  '00060': 'Discharge',
  '63680': 'Turbidity',
  '00095': 'Specific conductance',
}

function timestamp(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  })
}

export function CurrentView() {
  const [data, setData] = useState<LatestObservations | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [prediction, setPrediction] = useState<BloomPrediction | null>(null)
  const [predictionError, setPredictionError] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now)

  useEffect(() => {
    let stopped = false
    let nextPoll: number | undefined
    let controller: AbortController | undefined
    let inFlight = false

    async function load() {
      if (stopped || inFlight) return
      window.clearTimeout(nextPoll)
      inFlight = true
      const request = new AbortController()
      controller = request
      const timeout = window.setTimeout(() => request.abort(), 20_000)
      try {
        const [observations, model] = await Promise.allSettled([
          fetchLatestObservations(request.signal),
          fetchLatestPrediction(request.signal),
        ])
        if (stopped) return
        if (observations.status === 'fulfilled') {
          setData(observations.value)
          setError(null)
        } else {
          setError('Unable to refresh readings.')
        }
        if (model.status === 'fulfilled') {
          setPrediction(model.value)
          setPredictionError(null)
        } else {
          setPrediction(null)
          setPredictionError('Prediction unavailable. Retrying automatically on the next update.')
        }
      } finally {
        window.clearTimeout(timeout)
        inFlight = false
        if (!stopped) {
          setNow(Date.now())
          nextPoll = window.setTimeout(() => void load(), 15_000)
        }
      }
    }

    function resume() {
      if (document.visibilityState === 'visible') void load()
    }

    document.addEventListener('visibilitychange', resume)
    window.addEventListener('online', resume)
    void load()
    return () => {
      stopped = true
      controller?.abort()
      window.clearTimeout(nextPoll)
      document.removeEventListener('visibilitychange', resume)
      window.removeEventListener('online', resume)
    }
  }, [])

  const readings = new Map(data?.readings.map((reading) => [reading.parameter_code, reading]))

  return (
    <div className="current">
      <header className="current__intro" aria-labelledby="current-title">
        <p id="current-title" className="current__intro-line">
          <span className="current__intro-label">USGS</span>
          <span className="current__intro-station">{data?.station_id ?? 'Loading…'}</span>
          <span className="current__intro-muted">· USGS typically publishes hourly · page refreshes every 15s</span>
        </p>
        <div className="current__intro-aside">
          <p className={`chip chip--compact ${error ? 'chip--warn' : data ? 'chip--ok' : ''}`} role="status">
            {error ? 'Reconnecting' : data ? 'Connected' : 'Connecting…'}
          </p>
          {data && (
            <time className="current__intro-fetched" dateTime={data.fetched_at} title="Last page refresh; observation times appear on each reading">
              {timestamp(data.fetched_at)}
            </time>
          )}
        </div>
      </header>

      <BloomPredictionCard prediction={prediction} error={predictionError} updatedAt={now} />

      {error && <p className="current__notice" role="alert">{error}{data ? ' Showing previously fetched readings.' : ''}</p>}
      {!data && !error && <p role="status">Loading observations…</p>}
      {data?.readings.length === 0 && <p className="current__notice" role="status">No readings available for this station.</p>}

      {data && <section className="current__grid" aria-label="Latest measurements">
        {data.requested_parameters.map((code) => {
          const reading = readings.get(code)
          const stale = reading && isObservationStale(reading.observed_at, now, data.stale_after_seconds)
          return (
            <article className="card current__reading" key={code}>
              <div className="current__reading-heading">
                <h3>{PARAMETERS[code] ?? code}</h3>
                {stale && <span className="chip chip--warn" title="No new reading for over two hours">Update overdue</span>}
              </div>
              <p className="current__value">{reading?.value != null
                ? reading.value.toLocaleString(undefined, { maximumFractionDigits: 3 })
                : 'No data'}</p>
              <p className="current__unit">{reading?.unit ?? 'No stored measurement'}</p>
              {reading ? <>
                <p className="current__note">Observed <time dateTime={reading.observed_at}>{timestamp(reading.observed_at)}</time></p>
                <p className="current__note">{reading.approval_status ?? 'Approval status unavailable'}{reading.qualifier ? ` · ${reading.qualifier}` : ''}</p>
              </> : <p className="current__note">No reading available.</p>}
              <p className="current__code">USGS {code}</p>
            </article>
          )
        })}
      </section>}
      <p className="current__note">USGS provisional measurements may be revised. Pigment fluorescence is an indicator, not confirmation of a harmful algal bloom.</p>
    </div>
  )
}
