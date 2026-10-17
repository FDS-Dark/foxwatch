import { useCallback, useEffect, useState } from 'react'
import {
  createPrediction,
  listEventLabels,
  listModels,
  listScenePredictions,
  retrainModel,
  reviewPrediction,
} from '../data/demo/reviewStore'
import type { HumanLabel, ModelList, Prediction, ReviewDecision } from '../data/types/review'
import { AnalysisRunsPanel } from '../components/review/AnalysisRunsPanel'
import { AnalystReviewPanel } from '../components/review/AnalystReviewPanel'
import { LabelsList } from '../components/review/LabelsList'
import { DEMO_EVENT_ID, DEMO_SCENE_ID } from '../config/demo'

const STEPS = [
  { title: 'Predict', body: 'Active model scores the scene' },
  { title: 'Human review', body: 'Analyst approves or denies' },
  { title: 'Retrain', body: 'Denials become training data' },
]

export function ReviewView() {
  const [models, setModels] = useState<ModelList | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [labels, setLabels] = useState<HumanLabel[]>([])
  const [labelsKey, setLabelsKey] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const load = useCallback(() => {
    setModels(listModels())
    setPredictions(listScenePredictions(DEMO_SCENE_ID))
    setLabels(listEventLabels(DEMO_EVENT_ID))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function run<T>(key: string, fn: () => T, done: (r: T) => string) {
    setBusy(key)
    setToast(null)
    try {
      const result = fn()
      load()
      setToast(done(result))
    } catch (e) {
      setToast(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const pending = predictions.filter((p) => p.review_status === 'pending_review')
  const reviewed = predictions.filter((p) => p.review_status !== 'pending_review')
  const unusedDenials = predictions.filter(
    (p) => p.review_status === 'denied' && !p.used_in_training_job_id,
  ).length
  const activeStep = pending.length ? 1 : unusedDenials ? 2 : 0

  const ordered = [...(models?.models ?? [])].reverse()

  return (
    <div className="review">
      <ol className="loop" aria-label="Feedback loop">
        {STEPS.map((s, i) => (
          <li
            key={s.title}
            className={`loop__step${i === activeStep ? ' is-active' : ''}`}
            aria-current={i === activeStep ? 'step' : undefined}
          >
            <span className="loop__num">{i + 1}</span>
            <span>
              <strong>{s.title}</strong>
              <span className="loop__body">{s.body}</span>
            </span>
          </li>
        ))}
      </ol>

      {toast ? (
        <p className="toast" role="status">
          {toast}
        </p>
      ) : null}

      <div className="review__grid">
        <section className="card" aria-labelledby="queue-title">
          <header className="card__header">
            <div>
              <h2 id="queue-title" className="card__title">
                Prediction queue
              </h2>
              <p className="card__sub">
                Scene <code>{DEMO_SCENE_ID}</code> · {pending.length} awaiting
                review · <span className="chip chip--fixture">UI demo</span>
              </p>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy !== null}
              onClick={() =>
                run('predict', () => createPrediction(DEMO_SCENE_ID), (p) =>
                  `New prediction from ${p.model_version_id}: ${p.predicted_class.replace('_', ' ')}`,
                )
              }
            >
              {busy === 'predict' ? 'Scoring…' : 'Run model on scene'}
            </button>
          </header>

          {pending.length === 0 ? (
            <p className="muted queue-empty">
              Nothing to review. Run the model to create a prediction.
            </p>
          ) : (
            <ul className="queue">
              {pending.map((p) => (
                <PredictionCard
                  key={p.prediction_id}
                  prediction={p}
                  disabled={busy !== null}
                  onDecide={(decision, notes) =>
                    run(
                      p.prediction_id,
                      () => reviewPrediction(p.prediction_id, decision, notes),
                      () =>
                        decision === 'denied'
                          ? 'Denied. This example is queued as training feedback.'
                          : 'Approved. The prediction can now be cited.',
                    )
                  }
                />
              ))}
            </ul>
          )}

          {reviewed.length ? (
            <details className="history">
              <summary>Review history ({reviewed.length})</summary>
              <ul>
                {[...reviewed].reverse().map((p) => (
                  <li key={p.prediction_id}>
                    <span className={`decision decision--${p.review_status}`}>
                      {p.review_status}
                    </span>
                    <span className="mono">{p.model_version_id}</span>
                    <span>score {p.score.toFixed(2)}</span>
                    {p.used_in_training_job_id ? (
                      <span className="chip chip--ok">used in training</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>

        <section className="card" aria-labelledby="lineage-title">
          <header className="card__header">
            <div>
              <h2 id="lineage-title" className="card__title">
                Model lineage
              </h2>
              <p className="card__sub">
                Each retrain creates a new version with provenance (in-browser demo).
              </p>
            </div>
          </header>

          <div className="retrain">
            <div>
              <span className="retrain__count">{unusedDenials}</span>
              <span className="retrain__label">
                denied example{unusedDenials === 1 ? '' : 's'} ready for
                training
              </span>
            </div>
            <button
              type="button"
              className="btn btn--fox"
              disabled={busy !== null || unusedDenials === 0}
              onClick={() =>
                run('retrain', () => retrainModel(1), (j) =>
                  `Retrained on ${j.denial_sample_ids.length} denial(s). ${j.new_model_version_id} is now active.`,
                )
              }
            >
              {busy === 'retrain' ? 'Retraining…' : 'Retrain with denials'}
            </button>
          </div>

          <ol className="lineage">
            {ordered.map((m) => {
              const active = m.model_version_id === models?.active_model_version_id
              const params = m.parameters_json as Record<string, number | string>
              const denials = (m.training_summary as { denial_count?: number })
                .denial_count
              return (
                <li key={m.model_version_id} className={active ? 'is-active' : undefined}>
                  <span className="lineage__node" aria-hidden="true" />
                  <div>
                    <p className="lineage__id">
                      <span className="mono">{m.model_version_id}</span>
                      {active ? <span className="chip chip--ok">Active</span> : null}
                    </p>
                    <p className="lineage__meta">
                      threshold {Number(params.threshold).toFixed(3)} · bias{' '}
                      {Number(params.elevated_bias).toFixed(3)}
                      {denials ? ` · trained on ${denials} denial(s)` : ' · baseline'}
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      </div>

      <h2 className="section-title">Scene labels &amp; overlay re-runs</h2>
      <div className="review__grid">
        <AnalystReviewPanel
          onLabelsChange={(next) => {
            setLabels(next)
            setLabelsKey((k) => k + 1)
          }}
        />
        <div className="stack">
          <LabelsList labels={labels} refreshKey={labelsKey} />
          <AnalysisRunsPanel labels={labels} />
        </div>
      </div>
    </div>
  )
}

function PredictionCard({
  prediction,
  disabled,
  onDecide,
}: {
  prediction: Prediction
  disabled: boolean
  onDecide: (d: ReviewDecision, notes?: string) => void
}) {
  const [notes, setNotes] = useState('')
  const elevated = prediction.predicted_class === 'proxy_elevated'
  const pct = Math.round(prediction.score * 100)
  const notesId = `notes-${prediction.prediction_id}`

  return (
    <li className="pred">
      <div
        className="gauge"
        style={{ ['--p' as string]: `${pct}%` }}
        role="img"
        aria-label={`Score ${prediction.score.toFixed(2)} out of 1`}
      >
        <span>{prediction.score.toFixed(2)}</span>
      </div>
      <div className="pred__body">
        <p className="pred__class">
          <span className={`chip ${elevated ? 'chip--algae' : 'chip--water'}`}>
            {elevated ? 'Proxy elevated' : 'Proxy normal'}
          </span>
          <span className="mono muted">{prediction.model_version_id}</span>
        </p>
        <label htmlFor={notesId} className="sr-only">
          Reviewer notes
        </label>
        <input
          id={notesId}
          className="pred__notes"
          placeholder="Reviewer note (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <div className="pred__actions">
          <button
            type="button"
            className="btn btn--approve"
            disabled={disabled}
            onClick={() => onDecide('approved', notes || undefined)}
          >
            ✓ Approve
          </button>
          <button
            type="button"
            className="btn btn--deny"
            disabled={disabled}
            onClick={() => onDecide('denied', notes || undefined)}
          >
            ✕ Deny
          </button>
        </div>
      </div>
    </li>
  )
}
