import { predictionBucket, type BloomPrediction } from '@/models/prediction'

export function BloomPredictionCard({ prediction, error, updatedAt }: {
  prediction: BloomPrediction | null
  error: string | null
  updatedAt: number
}) {
  const bucket = prediction?.status === 'available' ? predictionBucket(prediction.probability) : null
  const fallbackCount = prediction?.inputs.filter((input) => input.used_fallback).length ?? 0

  return (
    <section className="card bloom-prediction" aria-labelledby="bloom-prediction-title">
      <div>
        <p className="eyebrow">Logistic regression · Latest Tiger Data readings</p>
        <h2 id="bloom-prediction-title">Algal bloom prediction</h2>
        <p className="current__note">Recalculated with each automatic update, every 15 seconds.</p>
      </div>
      <div aria-live="polite" aria-atomic="true">
        {error ? <p className="current__notice">{error}</p>
          : prediction?.status === 'available' ? (
            <div className="bloom-prediction__result">
              <p className="bloom-prediction__score" title={`Full probability: ${prediction.probability}`}>
                <span className="sr-only">Model probability: </span>{prediction.probability.toFixed(4)}
              </p>
              <span className={`bloom-prediction__bucket bloom-prediction__bucket--${bucket}`}>
                {bucket === 'low' ? 'Low chance' : bucket === 'medium' ? 'Medium chance' : 'High chance'}
              </span>
            </div>
          ) : prediction?.status === 'unavailable' ? (
            <p className="current__notice">Prediction unavailable. No measured value for: {prediction.missing_features.map((name) => name.replaceAll('_', ' ')).join(', ')}.</p>
          ) : <p>Calculating prediction…</p>}
      </div>
      <p className="current__note">Low: &lt; 0.5 · Medium: 0.5 to &lt; 0.8 · High: ≥ 0.8</p>
      {prediction?.status === 'available' && <>
        <p className="current__note">Calculated <time dateTime={new Date(updatedAt).toISOString()}>{new Date(updatedAt).toLocaleTimeString()}</time>
          {fallbackCount > 0 && ` · Using last measured values for ${fallbackCount} ${fallbackCount === 1 ? 'feature' : 'features'}.`}
        </p>
        {prediction.inputs.some((input) => updatedAt - Date.parse(input.observed_at) > 30 * 60_000) &&
          <p className="current__note">Some input measurements are over 30 minutes old.</p>}
      </>}
      <p className="current__note">Experimental model score, not a confirmed bloom or calibrated risk. Trained on daily means; current inputs are instantaneous measurements.</p>
    </section>
  )
}
