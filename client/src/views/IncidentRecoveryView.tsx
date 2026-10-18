import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  IncidentRecoveryResponse,
  RecoveryPriority,
  RecoverySuggestion,
  SuggestionCategory,
} from '@/models/incidentRecovery'
import { BfiScoreChart } from '@/components/BfiScoreChart'
import { fetchBfiHealth } from '@/services/bfiService'
import { fetchIncidentRecovery } from '@/services/incidentRecoveryService'
import './IncidentRecoveryView.css'

const PRIORITY_LABEL: Record<RecoveryPriority, string> = {
  immediate: 'Immediate',
  short_term: 'Short term',
  long_term: 'Long term',
}

const CATEGORY_LABEL: Record<SuggestionCategory, string> = {
  algae_cleanup: 'Algae cleanup & bloom reduction',
  consequence_reduction: 'Reduce consequences',
}

function formatConditionValue(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const abs = Math.abs(value)
    if (abs >= 100) return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
    if (abs >= 10) return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  return String(value)
}

function passageBlurb(chunk: { retrieval_summary: string; text: string }): string {
  let raw = (chunk.retrieval_summary || '').trim()
  raw = raw.replace(/^This section explains [^.]+\.\s*/i, '')
  if (raw.length < 48) raw = chunk.text.slice(0, 280).trim()
  return raw.slice(0, 280)
}

function SuggestionCard({ item }: { item: RecoverySuggestion }) {
  return (
    <li className="bfi-passage recovery-suggestion">
      <p className="bfi-passage__head">
        <span className="bfi-passage__num" aria-hidden="true">
          •
        </span>
        <span>
          {item.title}
          <span className={`recovery-priority recovery-priority--${item.priority}`}>
            {PRIORITY_LABEL[item.priority] ?? item.priority}
          </span>
        </span>
      </p>
      <p>{item.rationale}</p>
      {item.actions.length > 0 ? (
        <ul className="recovery-suggestion__actions">
          {item.actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      ) : null}
      {item.caution ? <p className="recovery-suggestion__caution">{item.caution}</p> : null}
      {item.sources.length > 0 ? (
        <details className="recovery-suggestion__sources">
          <summary>Supporting sources ({item.sources.length})</summary>
          <ol className="bfi-passages bfi-passages--compact">
            {item.sources.map((src) => (
              <li key={src.chunk_id} className="bfi-passage">
                <p className="bfi-passage__head">
                  <span>{src.document_title || 'Research passage'}</span>
                  {src.section ? <span className="muted"> · {src.section}</span> : null}
                </p>
                <p className="bfi-passage__excerpt">{src.relevance || src.excerpt}</p>
                {src.relevance && src.excerpt ? (
                  <p className="muted bfi-passage__excerpt">{src.excerpt}</p>
                ) : null}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </li>
  )
}

export function IncidentRecoveryView() {
  const [geminiOn, setGeminiOn] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<IncidentRecoveryResponse | null>(null)
  const controller = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    controller.current?.abort()
    const ac = new AbortController()
    controller.current = ac
    setLoading(true)
    setError(null)
    try {
      const response = await fetchIncidentRecovery(
        { use_gemini: geminiOn !== false },
        { signal: ac.signal },
      )
      if (!ac.signal.aborted) setData(response)
    } catch (err) {
      if (!ac.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Could not load recovery suggestions.')
        setData(null)
      }
    } finally {
      if (!ac.signal.aborted) setLoading(false)
    }
  }, [geminiOn])

  useEffect(() => {
    fetchBfiHealth()
      .then((h) => setGeminiOn(h.gemini_configured === true))
      .catch(() => setGeminiOn(false))
  }, [])

  useEffect(() => {
    if (geminiOn === null) return
    void load()
  }, [geminiOn, load])

  useEffect(() => () => controller.current?.abort(), [])

  const recovery = data?.recovery
  const chunks = data?.evidence.supporting_chunks ?? []
  const bfi = data?.bfi
  const fullMax = bfi?.full_max_score ?? 12
  const pctFull =
    bfi?.favorability_percent_full ??
    (bfi?.score != null ? Math.round((bfi.score / fullMax) * 100) : undefined)

  const cleanup = recovery?.recovery_suggestions.filter((s) => s.category === 'algae_cleanup') ?? []
  const consequences =
    recovery?.recovery_suggestions.filter((s) => s.category === 'consequence_reduction') ?? []

  return (
    <div className="bfi-page">
      <header className="bfi-page__toolbar">
        <p className="muted bfi-page__lede">
          Uses today&apos;s bloom favorability score and live Fox River conditions to suggest ways to
          clean up algae and limit harm to people and the ecosystem. Gemini drafts actions from matched
          research and each item links to passages that explain why it applies. This is not an official
          emergency order.
        </p>
        <button type="button" className="btn btn--compact" disabled={loading} onClick={() => void load()}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      {error ? (
        <p className="bfi-page__error" role="alert">
          {error}
        </p>
      ) : null}

      {bfi && !loading ? (
        <section className="card recovery-snapshot" aria-label="Score and live inputs">
          <div className="recovery-snapshot__score">
            <header className="recovery-snapshot__head">
              <h2 className="recovery-snapshot__title">Today&apos;s bloom favorability</h2>
              <p className="recovery-snapshot__tier">{bfi.classification}</p>
            </header>
            <BfiScoreChart
              compact
              score={bfi.score ?? 0}
              favorabilityPercentFull={pctFull}
              driversReporting={bfi.drivers_reporting}
              factors={bfi.factors as Parameters<typeof BfiScoreChart>[0]['factors']}
            />
          </div>
          <div className="recovery-snapshot__inputs">
            <h3 className="recovery-snapshot__subtitle">Live inputs</h3>
            <dl className="recovery-conditions">
              {(data?.current_conditions ?? [])
                .filter((row) => row.kind === 'input')
                .map((row) => (
                  <div key={row.label} className="recovery-conditions__row">
                    <dt>{row.label}</dt>
                    <dd>
                      <span className="recovery-conditions__value">{formatConditionValue(row.value)}</span>
                      {row.note ? <span className="recovery-conditions__note">{row.note}</span> : null}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>
        </section>
      ) : loading ? (
        <p className="muted" role="status">
          Loading live score and recovery suggestions…
        </p>
      ) : null}

      {recovery ? (
        <>
          <section className="card bfi-narrative">
            <h3 className="card__title">Situation summary</h3>
            <p>{recovery.situation_summary}</p>
            {recovery.confidence?.reason ? (
              <p className="muted bfi-narrative__note">
                Confidence is {recovery.confidence.level ?? 'unknown'} at{' '}
                {recovery.confidence.percent ?? 'unknown'} percent. {recovery.confidence.reason}
              </p>
            ) : null}
          </section>

          {cleanup.length > 0 ? (
            <section className="card">
              <h3 className="card__title">{CATEGORY_LABEL.algae_cleanup}</h3>
              <ol className="bfi-passages">{cleanup.map((item) => <SuggestionCard key={item.title} item={item} />)}</ol>
            </section>
          ) : null}

          {consequences.length > 0 ? (
            <section className="card">
              <h3 className="card__title">{CATEGORY_LABEL.consequence_reduction}</h3>
              <ol className="bfi-passages">
                {consequences.map((item) => (
                  <SuggestionCard key={item.title} item={item} />
                ))}
              </ol>
            </section>
          ) : null}

          {recovery.monitoring_recommendations.length > 0 ? (
            <section className="card">
              <h3 className="card__title">Monitoring follow-up</h3>
              <ul className="recovery-suggestion__actions">
                {recovery.monitoring_recommendations.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="card bfi-evidence">
            <h3 className="card__title">Research passages used</h3>
            <p className="muted bfi-evidence__intro">{data?.evidence.context_summary}</p>
            {chunks.length === 0 ? (
              <p className="muted">No passages retrieved.</p>
            ) : (
              <ol className="bfi-passages">
                {chunks.map((chunk, i) => (
                  <li key={chunk.chunk_id} className="bfi-passage">
                    <p className="bfi-passage__head">
                      <span className="bfi-passage__num">{i + 1}</span>
                      <span>{chunk.metadata.document_title || 'Passage'}</span>
                    </p>
                    <p className="bfi-passage__excerpt">{passageBlurb(chunk)}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}
