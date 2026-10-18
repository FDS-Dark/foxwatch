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
      if (!request.signal.aborted) setError('The research evidence could not be loaded. Check the API and try again.')
    } finally {
      if (!request.signal.aborted) setLoading(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void ask(draft)
  }

  const questions = [
    `Explain the satellite comparison for segment ${segmentId}.`,
    'Does the improvement generalize? Where does the model fail?',
    'What was measured, when, and what does RFU mean?',
  ]

  return <div className="xray-investigate">
    <section className="card">
      <div className="xray-row"><div><p className="eyebrow">X-Ray the Bay · traceable research</p><h2>Ask what the evidence supports</h2></div>
        <span className="chip">Stored research evidence</span></div>
      <p>Answers are assembled from the recorded FLAMe observations, held-out model errors, and research reports. They include limitations and links to the underlying records.</p>
      <p className="muted">This is a bounded research explainer, not a live AI chat or a current-bloom assessment. Answers may disclose the reveal results.</p>
      <div className="xray-row" style={{ marginTop: '1rem' }}><label>Case <select value={segmentId} onChange={e => {
        controller.current?.abort(); setLoading(false); setSegmentId(Number(e.target.value)); setAnswer(null); setQuestion(''); setError(null)
      }}><option value={32}>Segment 32 · plume recovery</option><option value={31}>Segment 31 · failure case</option><option value={17}>Segment 17 · typical case</option></select></label>
        <a className="btn" href={`#/replay?segment=${segmentId}`}>Open this experiment →</a></div>
    </section>
    <section className="card"><h3>Explore the research</h3><div className="xray-sources">{questions.map(q => <button className="btn" key={q} onClick={() => { setDraft(q); void ask(q) }}>{q}</button>)}</div></section>
    <section className="card">
      <form className="composer" onSubmit={submit}><label className="sr-only" htmlFor="xray-question">Question about the research</label>
        <input id="xray-question" maxLength={1000} value={draft} onChange={e => setDraft(e.target.value)} placeholder="Why did the satellite model improve segment 32?" />
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
