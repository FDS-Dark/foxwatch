import { useCallback, useEffect, useState } from 'react'
import type { HumanLabel, ModelList, Prediction, ReviewDecision } from '../data/types/review'
import {
  fetchMlModels,
  fetchMlPredictions,
  retrainMlFromDenials,
  resetLatestMlRetrain,
  runMlPredictionForReview,
  submitMlReview,
} from '../services/reviewService'
import { AnalysisRunsPanel } from '../components/review/AnalysisRunsPanel'
import { AnalystReviewPanel } from '../components/review/AnalystReviewPanel'
import { LabelsList } from '../components/review/LabelsList'
import { listEventLabels } from '../data/demo/reviewStore'
import { DEMO_EVENT_ID, DEMO_SCENE_ID } from '../config/demo'

const STEPS = [
  { title: 'Predict', body: 'Score current station readings' },
  { title: 'Human review', body: 'Approve or correct predictions' },
  { title: 'Retrain', body: 'Update the model with corrections' },
]

export function ReviewView() {
  const [models, setModels] = useState<ModelList | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [labels, setLabels] = useState<HumanLabel[]>([])
  const [labelsKey, setLabelsKey] = useState(0)
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
      setLabels(listEventLabels(DEMO_EVENT_ID))
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
          Could not load the review queue. Try again.
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
                Station <code>{DEMO_SCENE_ID}</code> · {pending.length} awaiting review ·{' '}
                <span className="chip chip--ok">Station model</span>
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
                    `New prediction (${p.model_version_id}): ${p.predicted_class.replace('proxy_', '')} · p=${p.score.toFixed(2)}`,
                )
              }
            >
              {busy === 'predict' ? 'Scoring…' : 'Run model on live conditions'}
            </button>
          </header>

          {pending.length === 0 ? (
            <p className="muted queue-empty">
              No predictions awaiting review.
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
                          ? 'Denied — queued as a refit correction (opposite label).'
                          : 'Approved — recorded; not used for refit.',
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
                      <span className="chip chip--ok">used in refit</span>
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
                Denied predictions become corrections for the next model version.
              </p>
            </div>
          </header>

          <div className="retrain">
            <div>
              <span className="retrain__count">{unusedDenials}</span>
              <span className="retrain__label">
                denied example{unusedDenials === 1 ? '' : 's'} ready for refit
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
                {busy === 'retrain' ? 'Refitting…' : 'Refit with denials'}
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
                  {busy === 'reset-retrain' ? 'Resetting…' : 'Reset latest retrain'}
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
                      <span className="mono">{m.model_version_id}</span>
                      {active ? <span className="chip chip--ok">Active</span> : null}
                    </p>
                    <p className="lineage__meta">
                      {m.name}
                      {summary.training_rows ? ` · ${summary.training_rows} training rows` : ''}
                      {summary.human_feedback_rows
                        ? ` · +${summary.human_feedback_rows} human correction(s)`
                        : ' · baseline CSV'}
                    </p>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      </div>

      <details><summary>Satellite annotation prototype</summary>
      <p className="muted">
        Demo annotations; separate from station-model retraining.
      </p>
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
      </details>
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
            ✕ Deny (use for refit)
          </button>
        </div>
      </div>
    </li>
  )
}
