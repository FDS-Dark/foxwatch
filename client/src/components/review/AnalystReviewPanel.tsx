import { useCallback, useState, type FormEvent } from 'react'
import { createSceneLabel, listEventLabels } from '../../data/demo/reviewStore'
import type { HumanLabel, LabelTaxonomy } from '../../data/types/review'
import {
  DEMO_EVENT_ID,
  DEMO_PARENT_RUN_ID,
  DEMO_SCENE_ID,
  TAXONOMY_OPTIONS,
} from '../../config/demo'

type Props = {
  onLabelsChange: (labels: HumanLabel[]) => void
}

export function AnalystReviewPanel({ onLabelsChange }: Props) {
  const [taxonomy, setTaxonomy] = useState<LabelTaxonomy>(
    'proxy_elevated_plausible',
  )
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(() => {
    const next = listEventLabels(DEMO_EVENT_ID)
    onLabelsChange(next)
    return next
  }, [onLabelsChange])

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      const created = createSceneLabel(DEMO_SCENE_ID, {
        event_id: DEMO_EVENT_ID,
        source_run_id: DEMO_PARENT_RUN_ID,
        taxonomy,
        confidence: 'medium',
        notes: notes.trim() || undefined,
        status: 'published',
      })
      refresh()
      setMessage(`Published label ${created.label_id}`)
      setNotes('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Failed to save label')
    } finally {
      setBusy(false)
    }
  }

  const selectedHint = TAXONOMY_OPTIONS.find((o) => o.value === taxonomy)?.hint

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Analyst review</h2>
        <p className="panel__lede">
          Human-in-the-loop labels (stored in this browser session only).
        </p>
      </header>

      <form className="form" onSubmit={onSubmit}>
        <label className="field">
          <span>Taxonomy</span>
          <select
            value={taxonomy}
            onChange={(ev) =>
              setTaxonomy(ev.target.value as LabelTaxonomy)
            }
            disabled={busy}
          >
            {TAXONOMY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {selectedHint ? (
            <span className="field__hint">{selectedHint}</span>
          ) : null}
        </label>

        <label className="field">
          <span>Notes</span>
          <textarea
            rows={3}
            value={notes}
            onChange={(ev) => setNotes(ev.target.value)}
            disabled={busy}
            placeholder="Optional context for other analysts"
          />
        </label>

        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Saving…' : 'Publish label'}
        </button>
        {message ? <p className="form__message">{message}</p> : null}
      </form>
    </section>
  )
}
