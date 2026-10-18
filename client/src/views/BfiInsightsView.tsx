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
  const fullMax = data?.bfi.full_max_score ?? 12
  const pctFull =
    data?.bfi.favorability_percent_full ??
    (data ? Math.round((data.bfi.score / fullMax) * 100) : undefined)
  const driversReporting = data?.bfi.drivers_reporting
  const driversTotal = data?.bfi.drivers_total ?? 6

  return (
    <div className="bfi-page">
      <header className="bfi-page__toolbar">
        <p className="muted bfi-page__lede">
          A rule-based check. Given today&apos;s Fox River and weather inputs, how many known
          &ldquo;bloom-friendly&rdquo; conditions are met? This is not a bloom forecast. It does not
          say a bloom will happen, only whether the environment looks favorable compared to research
          thresholds.
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

      <details className="card bfi-how">
        <summary>How bloom favorability is scored</summary>
        <p className="bfi-how__lede">
          Six drivers can each add 0, 1, or 2 points (2 is most favorable for blooms). The meter and
          percentage always use the full 12-point scale. Drivers without readings today count as 0 points.
        </p>
        <p className="bfi-how__subhead">Overall tiers when all six drivers are present (12 points max)</p>
        <ul className="bfi-how__tiers">
          <li>0 to 3 points · Low favorability</li>
          <li>4 to 7 points · Moderate favorability</li>
          <li>8 to 10 points · High favorability</li>
          <li>11 to 12 points · Very high favorability</li>
        </ul>
        <p className="bfi-how__subhead">Points per driver</p>
        <ul className="bfi-how__drivers">
          <li>
            <strong>Water temperature</strong>
            <ul>
              <li>Below 20&nbsp;°C · 0 pts · typical / cooler</li>
              <li>20 to 25&nbsp;°C · 1 pt · warming</li>
              <li>Above 25&nbsp;°C · 2 pts · bloom-favoring</li>
            </ul>
          </li>
          <li>
            <strong>Phosphorus (dissolved)</strong>
            <ul>
              <li>Below 20&nbsp;µg/L · 0 pts</li>
              <li>20 to 50&nbsp;µg/L · 1 pt</li>
              <li>Above 50&nbsp;µg/L · 2 pts</li>
            </ul>
          </li>
          <li>
            <strong>Nitrogen (nitrate + nitrite)</strong>
            <ul>
              <li>Below 0.5&nbsp;mg/L · 0 pts</li>
              <li>0.5 to 1.0&nbsp;mg/L · 1 pt</li>
              <li>Above 1.0&nbsp;mg/L · 2 pts</li>
            </ul>
          </li>
          <li>
            <strong>Streamflow vs seasonal median</strong>
            <ul>
              <li>Above median · 0 pts</li>
              <li>Within ±10% of median · 1 pt</li>
              <li>Below 90% of median · 2 pts · slower flush</li>
            </ul>
          </li>
          <li>
            <strong>Rainfall, past 7 days</strong>
            <ul>
              <li>Under 0.5&nbsp;in · 0 pts</li>
              <li>0.5 to 2&nbsp;in · 1 pt</li>
              <li>Over 2&nbsp;in · 2 pts · runoff loading</li>
            </ul>
          </li>
          <li>
            <strong>Sunlight</strong>
            <ul>
              <li>Low · 0 pts</li>
              <li>Moderate · 1 pt</li>
              <li>High · 2 pts</li>
            </ul>
          </li>
        </ul>
        <p className="muted bfi-how__note">
          Points reflect published drivers of cyanobacteria growth, not a direct measurement of algae in
          the bay. Pair with satellite views and official advisories when making decisions.
        </p>
      </details>

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
            {pctFull != null ? (
              <>
                <p className="bfi-hero__meter" aria-label={`${pctFull} percent of full twelve point score`}>
                  <span className="bfi-hero__meter-fill" style={{ width: `${Math.min(100, pctFull)}%` }} />
                  <span className="bfi-hero__meter-label">
                    {pctFull}% of full score · {data.bfi.score}/{fullMax} pts
                  </span>
                </p>
                {driversReporting != null && driversReporting < driversTotal ? (
                  <p className="muted bfi-hero__coverage">
                    Scored from {driversReporting} of {driversTotal} drivers with readings today. Unreported drivers stay at 0 points on the 12-point scale.
                  </p>
                ) : null}
              </>
            ) : null}
            <p className="bfi-hero__summary">{data.insights.executive_summary}</p>
            <p className="muted bfi-hero__confidence">
              Confidence {data.insights.confidence.level} ({data.insights.confidence.percent}%)
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
                favorabilityPercentFull={pctFull}
                driversReporting={driversReporting}
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
              Citations and supporting publications appear under Sources, not in this summary.
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
              Trusted agencies and programs that publish nutrient, flow, and health guidance for Wisconsin
              and Great Lakes waters. Each entry links to the live program page. When our indexed research
              library aligns with a program, you can open matching passages below that link.
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
                    {source.consistency === 'aligned' || source.consistency === 'partial' ? (
                      <p className="muted bfi-authority__consistency">
                        Indexed research{' '}
                        {source.consistency === 'aligned'
                          ? 'aligns with passages cited below'
                          : 'partially aligns with passages cited below'}
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
                                  {' '}
                                  · {[pub.authors, pub.year].filter(Boolean).join(', ')}
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
