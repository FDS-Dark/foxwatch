import { predictionBucket, type BloomPrediction } from '@/models/prediction'

export function BloomPredictionCard({ prediction, error, updatedAt }: {
  prediction: BloomPrediction | null
  error: string | null
  updatedAt: number
}) {
  const bucket = prediction?.status === 'available' ? predictionBucket(prediction.probability) : null
  const fallbackCount = prediction?.inputs.filter((input) => input.used_fallback).length ?? 0
  const percent =
    prediction?.status === 'available' ? Math.round(prediction.probability * 100) : null

  return (
    <section className="card bloom-prediction" aria-labelledby="bloom-prediction-title">
      <div>
        <p className="eyebrow">Experimental indicator</p>
        <h2 id="bloom-prediction-title">Algal bloom likelihood</h2>
        <p className="current__note">Updates with the latest station readings.</p>
      </div>
      <div aria-live="polite" aria-atomic="true">
        {error ? (
          <p className="current__notice">{error}</p>
        ) : prediction?.status === 'available' ? (
          <div className="bloom-prediction__result">
            <p className="bloom-prediction__score">
              <span className="sr-only">Likelihood: </span>
              {percent}%
            </p>
            <span className={`bloom-prediction__bucket bloom-prediction__bucket--${bucket}`}>
              {bucket === 'low' ? 'Unlikely' : bucket === 'medium' ? 'Possible' : 'More likely'}
            </span>
          </div>
        ) : prediction?.status === 'unavailable' ? (
          <p className="current__notice">
            Not enough recent data to score. Missing:{' '}
            {prediction.missing_features.map((name) => name.replaceAll('_', ' ')).join(', ')}.
          </p>
        ) : (
          <p>Calculating…</p>
        )}
      </div>
      <p className="current__note">
        Unlikely &lt; 50% · Possible 50–79% · More likely ≥ 80%. Not a confirmed bloom or health advisory.
      </p>
      {prediction?.status === 'available' && (
        <>
          <p className="current__note">
            Last calculated{' '}
            <time dateTime={new Date(updatedAt).toISOString()}>
              {new Date(updatedAt).toLocaleTimeString()}
            </time>
            {fallbackCount > 0 &&
              ` · ${fallbackCount} value${fallbackCount === 1 ? '' : 's'} from last good reading.`}
          </p>
          {prediction.inputs.some(
            (input) => updatedAt - Date.parse(input.observed_at) > 30 * 60_000,
          ) && <p className="current__note">Some inputs are more than 30 minutes old.</p>}
        </>
      )}
    </section>
  )
}
