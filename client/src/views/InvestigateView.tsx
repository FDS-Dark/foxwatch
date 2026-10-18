import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { XrayAnswer } from '@/models/xray'
import { askXray, xrayResourceUrl } from '@/services/xrayService'
import './XrayView.css'

export function InvestigateView() {
  const [segmentId, setSegmentId] = useState(() => {
    const id = Number(new URLSearchParams(window.location.hash.split('?')[1]).get('segment'))
    return [17, 31, 32].includes(id) ? id : 32
  })
  const [draft, setDraft] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<XrayAnswer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function ask(text: string) {
    const query = text.trim()
    if (!query) return
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setQuestion(query)
    setAnswer(null)
    setLoading(true)
    setError(null)
    try {
      const result = await askXray(query, segmentId, request.signal)
      if (!request.signal.aborted) setAnswer(result)
    } catch {
      if (!request.signal.aborted) setError('Could not load study materials. Try again in a moment.')
    } finally {
      if (!request.signal.aborted) setLoading(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void ask(draft)
  }

  const questions = [
    'How did satellite imagery compare to location-only on this transect?',
    'Where does the method work poorly?',
    'What does fluorescence (RFU) mean in this study?',
  ]

  return <div className="xray-investigate">
    <section className="card">
      <div className="xray-row"><div><p className="eyebrow">2025 survey · cited answers</p><h2>Ask about the study</h2></div>
        <span className="chip">Archived evidence</span></div>
      <p>Answers draw on boat measurements, satellite comparisons, and published methods—with links and caveats.</p>
      <p className="muted">June–July 2025 research only. Not live conditions or a bloom advisory.</p>
      <div className="xray-row" style={{ marginTop: '1rem' }}><label>Transect <select value={segmentId} onChange={e => {
        controller.current?.abort(); setLoading(false); setSegmentId(Number(e.target.value)); setAnswer(null); setQuestion(''); setError(null)
      }}><option value={32}>After plume (32)</option><option value={31}>Poor fit (31)</option><option value={17}>Typical (17)</option></select></label>
        <a className="btn" href="#/replay">Open X-Ray the Bay →</a></div>
    </section>
    <section className="card"><h3>Suggested questions</h3><div className="xray-sources">{questions.map(q => <button className="btn" key={q} onClick={() => { setDraft(q); void ask(q) }}>{q}</button>)}</div></section>
    <section className="card">
      <form className="composer" onSubmit={submit}><label className="sr-only" htmlFor="xray-question">Question about the research</label>
        <input id="xray-question" maxLength={1000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="Why did imagery help on this transect?" />
        <button className="btn btn--primary" disabled={!draft.trim() || loading}>{loading ? 'Reading…' : 'Ask'}</button></form>
    </section>
    {error && <p className="card" role="alert">{error}</p>}
    {loading && <p role="status">Reading the stored results…</p>}
    {answer && <article className="card xray-answer" aria-live="polite"><h3>{question}</h3>{answer.answer.map((paragraph, i) => <p key={i}>{paragraph}</p>)}
      {answer.sources.length > 0 && <div><h3>Supporting records</h3><div className="xray-sources">{answer.sources.map(source => <a key={source.id} href={xrayResourceUrl(source.url)} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</div></div>}
      {answer.limitations.length > 0 && <div className="xray-layer-note">{answer.limitations.map(limit => <p key={limit}>{limit}</p>)}</div>}
    </article>}
  </div>
}
