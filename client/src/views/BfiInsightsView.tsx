import { useCallback, useEffect, useState } from 'react'
import type { BfiInsightResponse } from '../data/types/bfi'

const DEMO_INPUT = {
  water_temperature_c: 27,
  phosphorus_ug_l: 75,
  nitrogen_mg_l: 1.2,
  streamflow_cfs: 80,
  seasonal_median_streamflow_cfs: 150,
  rainfall_7day_in: 2.5,
  solar_radiation_level: 'high',
}

function formatTags(tags: string[] | string | undefined): string {
  if (!tags) return '—'
  if (Array.isArray(tags)) return tags.join(', ')
  return String(tags).trim()
}

function formatSourceLine(s: BfiInsightResponse['insights']['sources'][number]): string {
  if (s.citation) return s.citation
  const title = s.title?.trim()
  if (!title) return ''
  const parts = [title]
  if (s.chapter) parts.push(s.chapter)
  if (s.section) parts.push(s.section)
  if (s.authors) parts.push(s.authors)
  const head = parts.join(' · ')
  return s.year ? `${head} (${s.year})` : head
}

export function BfiInsightsView() {
  const [data, setData] = useState<BfiInsightResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [apiOk, setApiOk] = useState<boolean | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/bfi/insights', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...DEMO_INPUT, use_gemini: true }),
      })
      if (!res.ok) {
        const detail = await res.text()
        throw new Error(detail || res.statusText)
      }
      setData((await res.json()) as BfiInsightResponse)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((h) => setApiOk(h.gemini_configured === true))
      .catch(() => setApiOk(false))
  }, [])

  return (
    <div className="bfi-insights">
      <section className="card" aria-labelledby="bfi-title">
        <header className="card__header">
          <div>
            <h2 id="bfi-title" className="card__title">
              Bloom favorability insights
            </h2>
            <p className="card__sub">
              BFI drivers, hybrid RAG evidence, and Gemini narrative (when{' '}
              <code>GEMINI_API_KEY</code> is set in repo-root <code>.env</code>).
            </p>
          </div>
          <span className={`chip ${apiOk ? 'chip--ok' : 'chip--warn'}`}>
            {apiOk === null
              ? 'Checking API…'
              : apiOk
                ? 'Gemini ready'
                : 'Gemini off · evidence mode'}
          </span>
        </header>

        <p className="muted">
          Demo inputs: warm water, elevated P/N, low discharge vs seasonal median,
          recent rain, high solar.
        </p>

        <button type="button" className="btn btn--primary" onClick={load} disabled={loading}>
          {loading ? 'Generating…' : 'Generate insights'}
        </button>

        {error ? (
          <p className="bfi-insights__error" role="alert">
            {error}. Start the API:{' '}
            <code>uvicorn main:app --reload --app-dir api</code>
          </p>
        ) : null}
      </section>

      {data ? (
        <>
          <section className="card card--tint">
            <h3 className="card__title">{data.bfi.classification}</h3>
            <p className="bfi-insights__score">
              Score {data.bfi.score}/{data.bfi.max_possible_score}
              {data.bfi.favorability_percent != null
                ? ` · ${data.bfi.favorability_percent}% favorability`
                : null}
            </p>
            <p>{data.insights.executive_summary}</p>
            {data.insights.bloom_assessment ? (
              <p className="muted">{data.insights.bloom_assessment}</p>
            ) : null}
            {data.bfi.reasons?.length ? (
              <ul className="bfi-insights__list bfi-insights__drivers">
                {data.bfi.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : null}
            <p className="muted">
              Confidence: {data.insights.confidence.level} ({data.insights.confidence.percent}
              %) — {data.insights.confidence.reason}
            </p>
            {data.insights.generation_mode ? (
              <p className="muted">Narrative mode: {data.insights.generation_mode}</p>
            ) : null}
          </section>

          <section className="card">
            <h3 className="card__title">Key contributing factors</h3>
            <ul className="bfi-insights__list">
              {data.insights.key_contributing_factors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <h4>Scientific interpretation</h4>
            <p>{data.insights.scientific_interpretation}</p>
          </section>

          <section className="card">
            <h3 className="card__title">Sources consulted</h3>
            <ul className="bfi-insights__sources">
              {data.insights.sources.map((s, i) => {
                const line = formatSourceLine(s)
                if (!line) return null
                return (
                  <li key={`${line}-${i}`}>{line}</li>
                )
              })}
            </ul>
          </section>

          <section className="card">
            <header className="card__header">
              <h3 className="card__title">Retrieved evidence</h3>
              <p className="card__sub">{data.evidence.context_summary}</p>
            </header>
            <ol className="evidence-cards">
              {data.evidence.supporting_chunks.map((chunk, i) => (
                <li key={chunk.chunk_id} className="evidence-card">
                  <div className="evidence-card__meta">
                    <span className="tag">Evidence {i + 1}</span>
                    {chunk.hybrid_score != null ? (
                      <span className="muted" title="Hybrid retrieval rank (not cosine similarity; can exceed 1)">
                        rank {Number(chunk.hybrid_score).toFixed(3)}
                      </span>
                    ) : null}
                  </div>
                  <p className="evidence-card__cite">
                    {chunk.metadata.document_title}
                    {chunk.metadata.chapter ? ` · ${chunk.metadata.chapter}` : ''}
                    {chunk.metadata.section ? ` · ${chunk.metadata.section}` : ''}
                  </p>
                  <p className="evidence-card__summary">{chunk.retrieval_summary}</p>
                  <details>
                    <summary>Passage</summary>
                    <p className="evidence-card__text">{chunk.text}</p>
                  </details>
                  <p className="evidence-card__tags">
                    Tags: {formatTags(chunk.tags)}
                    {chunk.matched_tags?.length
                      ? ` · matched: ${chunk.matched_tags.join(', ')}`
                      : ''}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </>
      ) : null}
    </div>
  )
}
