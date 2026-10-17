import { useCallback, useEffect, useState } from 'react'
import {
  listAnalysisRuns,
  triggerHumanInformedRerun,
} from '../../data/demo/reviewStore'
import type { AnalysisRun, HumanLabel } from '../../data/types/review'
import {
  DEMO_EVENT_ID,
  DEMO_PARENT_RUN_ID,
} from '../../config/demo'

type Props = {
  labels: HumanLabel[]
}

export function AnalysisRunsPanel({ labels }: Props) {
  const [runs, setRuns] = useState<AnalysisRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const loadRuns = useCallback(() => {
    const data = listAnalysisRuns(DEMO_EVENT_ID)
    setRuns(data)
    if (data.length > 0) {
      setSelectedRunId((prev) => prev ?? data[data.length - 1].run_id)
    }
  }, [])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  function onRerun() {
    setBusy(true)
    setMessage(null)
    try {
      const job = triggerHumanInformedRerun(DEMO_EVENT_ID, {
        parent_run_id: DEMO_PARENT_RUN_ID,
        adjustment: 'threshold_recalibration_v1',
      })
      if (job.status === 'failed') {
        throw new Error(job.message ?? 'Re-run failed')
      }
      loadRuns()
      if (job.run_id) {
        setSelectedRunId(job.run_id)
      }
      setMessage(job.message ?? `Created ${job.run_id}`)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Re-run failed')
    } finally {
      setBusy(false)
    }
  }

  const selected = runs.find((r) => r.run_id === selectedRunId)
  const publishedCount = labels.filter((l) => l.status === 'published').length

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Analysis runs</h2>
        <p className="panel__lede">
          Human-informed re-run creates a new <code>run_id</code> in this demo
          session (no server job).
        </p>
      </header>

      <div className="run-actions">
        <button
          type="button"
          className="btn btn--secondary"
          onClick={onRerun}
          disabled={busy || publishedCount === 0}
        >
          {busy ? 'Running…' : 'Trigger human-informed re-run'}
        </button>
        {publishedCount === 0 ? (
          <span className="field__hint">
            Publish at least one label to enable re-run.
          </span>
        ) : null}
      </div>

      {message ? <p className="form__message">{message}</p> : null}

      <label className="field">
        <span>Compare runs</span>
        <select
          value={selectedRunId ?? ''}
          onChange={(ev) => setSelectedRunId(ev.target.value)}
        >
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.run_id}
              {run.parent_run_id ? ` ← ${run.parent_run_id}` : ' (baseline)'}
            </option>
          ))}
        </select>
      </label>

      {selected ? (
        <div className="run-detail">
          <dl>
            <div>
              <dt>Method</dt>
              <dd>{selected.method}</dd>
            </div>
            <div>
              <dt>Created (UTC)</dt>
              <dd>{selected.created_at_utc}</dd>
            </div>
            {selected.parent_run_id ? (
              <div>
                <dt>Parent run</dt>
                <dd>{selected.parent_run_id}</dd>
              </div>
            ) : null}
          </dl>
          <details>
            <summary>parameters_json</summary>
            <pre>{JSON.stringify(selected.parameters_json, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </section>
  )
}
