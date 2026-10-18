import { useCallback, useEffect, useState } from 'react'
import type { ModelList, Prediction, ReviewDecision } from '../data/types/review'
import {
  fetchMlModels,
  fetchMlPredictions,
  retrainMlFromDenials,
  resetLatestMlRetrain,
  runMlPredictionForReview,
  submitMlReview,
} from '../services/reviewService'
import { STATION_SHORT } from '@/config/copy'
import { DEMO_SCENE_ID } from '../config/demo'

const STEPS = [
  { title: 'Score', body: 'Run the bloom indicator on live readings' },
  { title: 'Review', body: 'Agree or disagree with the score' },
  { title: 'Update', body: 'Optionally teach the model from disagreements' },
]

export function ReviewView() {
  const [models, setModels] = useState<ModelList | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [modelList, preds] = await Promise.all([
        fetchMlModels(),
        fetchMlPredictions(DEMO_SCENE_ID),
      ])
      setModels(modelList)
      setPredictions(preds)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Failed to load review queue')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function run<T>(key: string, fn: () => Promise<T>, done: (r: T) => string) {
    setBusy(key)
    setToast(null)
    try {
      const result = await fn()
      await load()
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
  const hasRetrainModels = (models?.models ?? []).some((m) => m.parent_model_version_id)

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

      {loadError ? (
        <p className="bfi-insights__error" role="alert">
          {loadError}. Reload the page once FoxWatch is running.
        </p>
      ) : null}

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
                {STATION_SHORT} · {pending.length} waiting for review
              </p>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy !== null}
              onClick={() =>
                void run(
                  'predict',
                  () => runMlPredictionForReview(DEMO_SCENE_ID),
                  (p) =>
                    `Queued: ${p.predicted_class === 'proxy_elevated' ? 'more likely bloom' : 'unlikely bloom'} (${Math.round(p.score * 100)}%).`,
                )
              }
            >
              {busy === 'predict' ? 'Scoring…' : 'Score live conditions'}
            </button>
          </header>

          {pending.length === 0 ? (
            <p className="muted queue-empty">
              Queue is empty. Score live conditions to add an item.
            </p>
          ) : (
            <ul className="queue">
              {pending.map((p) => (
                <PredictionCard
                  key={p.prediction_id}
                  prediction={p}
                  disabled={busy !== null}
                  onDecide={(decision, notes) =>
                    void run(
                      p.prediction_id,
                      () => submitMlReview(p.prediction_id, decision, notes),
                      () =>
                        decision === 'denied'
                          ? 'Marked disagree — can be used to update the model.'
                          : 'Marked agree — saved to the review log.',
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
                    <span>{Math.round(p.score * 100)}% likelihood</span>
                    {p.used_in_training_job_id ? (
                      <span className="chip chip--ok">used in update</span>
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
                Model versions
              </h2>
              <p className="card__sub">
                Updates keep prior training and add corrections from disagreements.
              </p>
            </div>
          </header>

          <div className="retrain">
            <div>
              <span className="retrain__count">{unusedDenials}</span>
              <span className="retrain__label">
                disagreement{unusedDenials === 1 ? '' : 's'} ready to teach the model
              </span>
            </div>
            <div className="retrain__actions">
              <button
                type="button"
                className="btn btn--fox"
                disabled={busy !== null || unusedDenials === 0}
                onClick={() =>
                  void run('retrain', () => retrainMlFromDenials(5), (j) =>
                    j.message
                      ? j.message
                      : `Refitted. ${j.new_model_version_id ?? ''} is now active.`,
                  )
                }
              >
                {busy === 'retrain' ? 'Updating…' : 'Update model from disagreements'}
              </button>
              {hasRetrainModels ? (
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={busy !== null}
                  title="Removes the newest refit model, restores the previous version, and frees denials for review again"
                  onClick={() =>
                    void run('reset-retrain', () => resetLatestMlRetrain(), (r) => r.message)
                  }
                >
                  {busy === 'reset-retrain' ? 'Restoring…' : 'Undo latest update'}
                </button>
              ) : null}
            </div>
          </div>

          <ol className="lineage">
            {ordered.map((m) => {
              const active = m.model_version_id === models?.active_model_version_id
              const summary = m.training_summary as {
                human_feedback_rows?: number
                training_rows?: number
                denial_count?: number
              }
              return (
                <li key={m.model_version_id} className={active ? 'is-active' : undefined}>
                  <span className="lineage__node" aria-hidden="true" />
                  <div>
                    <p className="lineage__id">
                      {m.parent_model_version_id ? 'Updated model' : 'Original model'}
                      {active ? <span className="chip chip--ok">In use</span> : null}
                    </p>
                    <p className="lineage__meta">
                      {summary.training_rows ? `${summary.training_rows} historical examples` : 'Baseline training set'}
                      {summary.human_feedback_rows
                        ? ` · ${summary.human_feedback_rows} analyst correction(s)`
                        : ''}
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
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
            {elevated ? 'Bloom likely' : 'Bloom unlikely'}
          </span>
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
            ✕ Disagree
          </button>
        </div>
      </div>
    </li>
  )
}
