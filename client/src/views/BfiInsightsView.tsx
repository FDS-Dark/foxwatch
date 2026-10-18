import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import type { BfiAskResponse, BfiInsightResponse } from '@/models/bfi'
import { BfiScoreChart } from '@/components/BfiScoreChart'
import { askBfiQuestion, fetchBfiHealth, fetchBfiInsights } from '@/services/bfiService'
import './BfiInsightsView.css'

const SUGGESTED_QUESTIONS = [
  'Why is phosphorus important for blooms here?',
  'How does streamflow change nutrient delivery?',
  'What does the current score mean for recreation?',
]

function passageBlurb(chunk: { retrieval_summary: string; text: string }): string {
  let raw = (chunk.retrieval_summary || '').trim()
  raw = raw.replace(/^This section explains [^.]+\.\s*/i, '')
  if (raw.length < 48) raw = chunk.text.slice(0, 280).trim()
  return raw.slice(0, 280)
}

function hashQuestion(): string {
  const query = window.location.hash.split('?')[1]
  if (!query) return ''
  const params = new URLSearchParams(query)
  return (params.get('q') || params.get('question') || '').trim()
}

export function BfiInsightsView() {
  const [data, setData] = useState<BfiInsightResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [geminiOn, setGeminiOn] = useState<boolean | null>(null)
  const [chatDraft, setChatDraft] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatTurns, setChatTurns] = useState<Array<{ question: string; response: BfiAskResponse }>>([])
  const askController = useRef<AbortController | null>(null)
  const prefillHandled = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchBfiInsights({ use_live_data: true, use_gemini: true }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBfiHealth()
      .then((h) => setGeminiOn(h.gemini_configured === true))
      .catch(() => setGeminiOn(false))
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => () => askController.current?.abort(), [])

  const ask = useCallback(async (text: string) => {
    const question = text.trim()
    if (!question) return
    askController.current?.abort()
    const controller = new AbortController()
    askController.current = controller
    setChatLoading(true)
    setChatError(null)
    try {
      const response = await askBfiQuestion(question, {
        use_live_data: true,
        use_gemini: geminiOn !== false,
        signal: controller.signal,
      })
      if (!controller.signal.aborted) {
        setChatTurns((prev) => [...prev, { question, response }])
        setChatDraft('')
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setChatError(err instanceof Error ? err.message : 'Could not answer right now.')
      }
    } finally {
      if (!controller.signal.aborted) setChatLoading(false)
    }
  }, [geminiOn])

  useEffect(() => {
    if (prefillHandled.current) return
    prefillHandled.current = true
    const prefill = hashQuestion()
    if (prefill) {
      setChatDraft(prefill)
      void ask(prefill)
    }
  }, [ask])

  function submitChat(event: FormEvent) {
    event.preventDefault()
    void ask(chatDraft)
  }

  const chunks = data?.evidence.supporting_chunks ?? []
  const authoritySources = data?.insights.sources ?? []
  const pct = data?.bfi.favorability_percent

  return (
    <div className="bfi-page">
      <header className="bfi-page__toolbar">
        <p className="muted bfi-page__lede">
          Live water readings scored against agency guidance and research, with an analyst-friendly summary.
        </p>
        <div className="bfi-page__toolbar-actions">
          <span className={`chip ${geminiOn ? 'chip--ok' : 'chip--warn'}`}>
            {geminiOn === null ? '…' : geminiOn ? 'AI summary on' : 'Sources only'}
          </span>
          <button type="button" className="btn btn--primary btn--compact" onClick={load} disabled={loading}>
            {loading ? 'Updating…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error ? (
        <p className="bfi-page__error" role="alert">
          {error}. Reload once FoxWatch is running.
        </p>
      ) : null}

      {!data && !error && !loading ? <p role="status">Loading…</p> : null}

      {data ? (
        <div className="bfi-page__grid">
          <section className="card bfi-hero" aria-labelledby="bfi-hero-title">
            <h2 id="bfi-hero-title" className="bfi-hero__title">
              {data.bfi.classification}
            </h2>
            {pct != null ? (
              <p className="bfi-hero__meter" aria-label={`${pct} percent favorability`}>
                <span className="bfi-hero__meter-fill" style={{ width: `${Math.min(100, pct)}%` }} />
                <span className="bfi-hero__meter-label">{pct}% favorability</span>
              </p>
            ) : null}
            <p className="bfi-hero__summary">{data.insights.executive_summary}</p>
            <p className="muted bfi-hero__confidence">
              Confidence: {data.insights.confidence.level} ({data.insights.confidence.percent}%)
            </p>
          </section>

          <div className="bfi-score-row">
            <section className="card bfi-drivers">
              <h3 className="card__title">What drove the score</h3>
              <ul className="bfi-drivers__list">
                {(data.bfi.reasons?.length ? data.bfi.reasons : data.insights.key_contributing_factors).map(
                  (line) => (
                    <li key={line}>{line}</li>
                  ),
                )}
              </ul>
            </section>

            <section className="card bfi-chart-card">
              <BfiScoreChart
                score={data.bfi.score}
                maxScore={data.bfi.max_possible_score}
                favorabilityPercent={pct ?? undefined}
                factors={data.bfi.factors}
              />
            </section>
          </div>

          <section className="card bfi-narrative">
            <h3 className="card__title">
              {geminiOn && data.insights.rag_grounded ? 'Analyst interpretation' : 'Interpretation'}
            </h3>
            <p>{data.insights.scientific_interpretation}</p>
            <p className="muted bfi-narrative__note">
              Citations and supporting publications appear under Sources—not in this summary.
            </p>
          </section>

          <section className="card bfi-chat" aria-labelledby="bfi-chat-title">
            <h3 id="bfi-chat-title" className="card__title">
              Ask about drivers &amp; research
            </h3>
            <p className="muted bfi-chat__intro">
              Questions use today&apos;s favorability inputs plus literature passages matched to your question.
            </p>
            <div className="bfi-chat__suggestions">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button key={q} type="button" className="btn btn--compact" disabled={chatLoading} onClick={() => void ask(q)}>
                  {q}
                </button>
              ))}
            </div>
            <form className="composer bfi-chat__composer" onSubmit={submitChat}>
              <label className="sr-only" htmlFor="bfi-question">
                Question about bloom favorability
              </label>
              <input
                id="bfi-question"
                maxLength={1000}
                value={chatDraft}
                onChange={(e) => setChatDraft(e.target.value)}
                placeholder="e.g. How does recent rainfall affect phosphorus loading?"
                disabled={chatLoading}
              />
              <button type="submit" className="btn btn--primary" disabled={!chatDraft.trim() || chatLoading}>
                {chatLoading ? 'Reading…' : 'Ask'}
              </button>
            </form>
            {chatError ? (
              <p className="bfi-page__error" role="alert">
                {chatError}
              </p>
            ) : null}
            {chatTurns.length > 0 ? (
              <div className="bfi-chat__thread" aria-live="polite">
                {chatTurns.map((turn, turnIndex) => (
                  <article key={`${turnIndex}-${turn.question}`} className="bfi-chat__turn">
                    <p className="bfi-chat__q">{turn.question}</p>
                    <div className="bfi-chat__a">{turn.response.answer}</div>
                    {turn.response.limitations.length > 0 ? (
                      <p className="muted bfi-chat__limits">{turn.response.limitations.join(' ')}</p>
                    ) : null}
                    {turn.response.supporting_chunks.length > 0 ? (
                      <details className="bfi-chat__sources">
                        <summary>Passages used ({turn.response.supporting_chunks.length})</summary>
                        <ol className="bfi-passages bfi-passages--compact">
                          {turn.response.supporting_chunks.map((chunk, i) => (
                            <li key={chunk.chunk_id} className="bfi-passage">
                              <p className="bfi-passage__head">
                                <span className="bfi-passage__num">{i + 1}</span>
                                <span>{chunk.metadata.document_title}</span>
                              </p>
                              <p className="bfi-passage__excerpt">{passageBlurb(chunk)}</p>
                            </li>
                          ))}
                        </ol>
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <section className="card bfi-evidence">
            <h3 className="card__title">Sources</h3>
            <p className="muted bfi-evidence__intro">
              Official programs found on the web (or curated .gov links if search is off). Internal research passages
              below each source show whether the indexed literature is consistent—not the primary citation.
            </p>
            {authoritySources.length === 0 ? (
              <p className="muted">No sources retrieved yet.</p>
            ) : (
              <ol className="bfi-authority-sources">
                {authoritySources.map((source) => (
                  <li key={`${source.name}-${source.organization}`} className="bfi-authority">
                    <p className="bfi-authority__head">
                      <strong>{source.name}</strong>
                      {source.organization ? (
                        <span className="muted"> · {source.organization}</span>
                      ) : null}
                    </p>
                    {source.url ? (
                      <p className="bfi-authority__link">
                        <a href={source.url} target="_blank" rel="noreferrer">
                          View program / guidance ↗
                        </a>
                      </p>
                    ) : null}
                    <p className="bfi-authority__summary">{source.summary}</p>
                    {source.consistency ? (
                      <p className="muted bfi-authority__consistency">
                        Internal research check:{' '}
                        {source.consistency === 'aligned'
                          ? 'consistent with retrieved passages'
                          : source.consistency === 'partial'
                            ? 'partially consistent'
                            : 'not yet matched to passages'}
                      </p>
                    ) : null}
                    {source.backing_publications && source.backing_publications.length > 0 ? (
                      <div className="bfi-authority__backing">
                        <p className="bfi-authority__backing-label">Related publications (internal index)</p>
                        <ul>
                          {source.backing_publications.map((pub) => (
                            <li key={pub.title}>
                              {pub.title}
                              {pub.authors || pub.year ? (
                                <span className="muted">
                                  {' '}
                                  — {[pub.authors, pub.year].filter(Boolean).join(', ')}
                                </span>
                              ) : null}
                              {pub.section ? <span className="muted"> · {pub.section}</span> : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {source.evidence_indices?.length ? (
                      <details className="bfi-authority__passages">
                        <summary>Consistency passages ({source.evidence_indices.length})</summary>
                        <ol className="bfi-passages bfi-passages--compact">
                          {source.evidence_indices.map((idx) => {
                            const chunk = chunks[idx - 1]
                            if (!chunk) return null
                            return (
                              <li key={chunk.chunk_id} className="bfi-passage">
                                <p className="bfi-passage__excerpt">{passageBlurb(chunk)}</p>
                                <details>
                                  <summary>Full passage</summary>
                                  <p className="bfi-passage__full">{chunk.text}</p>
                                </details>
                              </li>
                            )
                          })}
                        </ol>
                      </details>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      ) : null}
    </div>
  )
}
