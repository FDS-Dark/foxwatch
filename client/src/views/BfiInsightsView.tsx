import { useCallback, useEffect, useState } from 'react'
import type { BfiInsightResponse } from '@/models/bfi'
import { fetchBfiHealth, fetchBfiInsights } from '@/services/bfiService'

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

function formatObservedAt(iso: string | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
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
      setData(
        await fetchBfiInsights({ use_live_data: true, use_gemini: true }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBfiHealth()
      .then((h) => setApiOk(h.gemini_configured === true))
      .catch(() => setApiOk(false))
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="bfi-insights">
      <section className="card" aria-labelledby="bfi-title">
        <header className="card__header">
          <div>
            <h2 id="bfi-title" className="card__title">
              Bloom favorability insights
            </h2>
            <p className="card__sub">
              BFI scored from live Tiger Data at Green Bay, hybrid RAG evidence, and Gemini
              narrative (when <code>GEMINI_API_KEY</code> is set in repo-root <code>.env</code>).
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
          Drivers are read from the same USGS parameters ingested into Tiger (temperature,
          nutrients, discharge). Seasonal median flow comes from historical 00060 in Tiger; solar
          uses a month-based proxy until irradiance is ingested.
        </p>

        <button type="button" className="btn btn--primary" onClick={load} disabled={loading}>
          {loading ? 'Generating…' : 'Refresh insights'}
        </button>

        {error ? (
          <p className="bfi-insights__error" role="alert">
            {error}. Ensure the API is running with Tiger configured:{' '}
            <code>cd api && uv run python main.py</code>
          </p>
        ) : null}
      </section>

      {data?.inputs_provenance?.station_readings?.length ? (
        <section className="card">
          <h3 className="card__title">Live inputs (Tiger Data)</h3>
          <ul className="bfi-insights__list">
            {data.inputs_provenance.station_readings.map((row) => (
              <li key={row.parameter_code}>
                <strong>{row.parameter_code}</strong> → {row.bfi_field}:{' '}
                {row.value != null ? String(row.value) : '—'}
                {row.unit ? ` ${row.unit}` : ''}
                {row.observed_at ? ` · ${formatObservedAt(String(row.observed_at))}` : ''}
                {row.used_fallback ? ' · last known value' : ''}
              </li>
            ))}
          </ul>
          {data.inputs_provenance.seasonal_median_streamflow_cfs != null ? (
            <p className="muted">
              Seasonal median discharge (this month, Tiger history):{' '}
              {Number(data.inputs_provenance.seasonal_median_streamflow_cfs).toFixed(0)} ft³/s
            </p>
          ) : null}
          {data.inputs_provenance.solar_radiation_note ? (
            <p className="muted">{data.inputs_provenance.solar_radiation_note}</p>
          ) : null}
        </section>
      ) : null}

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
            {data.gemini_status ? (
              <p className="muted">Gemini: {data.gemini_status}</p>
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
