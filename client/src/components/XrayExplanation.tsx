import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import type { ExplanationSelection, LiveExplanation } from '@/models/xrayLive'
import { explainLivePoint, xrayResourceUrl } from '@/services/xrayService'

const QUESTIONS = ['What explains this prediction?', 'How reliable is this location?', 'How does the satellite help?']

export function XrayExplanation({ selection, currentRunId, onClose }: {
  selection: ExplanationSelection; currentRunId: string; onClose: () => void
}) {
  const [answer, setAnswer] = useState<LiveExplanation>()
  const [question, setQuestion] = useState(QUESTIONS[0])
  const [draft, setDraft] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [source, setSource] = useState<string>()
  const heading = useRef<HTMLHeadingElement>(null)
  const { runId, lat, lon } = selection
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    const controller = new AbortController()
    explainLivePoint(runId, lat, lon, question, controller.signal)
      .then(result => { if (!controller.signal.aborted) setAnswer(result) }).catch(err => {
        if (controller.signal.aborted) return
        const status = axios.isAxiosError(err) ? err.response?.status : undefined
        setError(status === 404 || status === 405 ? 'This API process does not have the explanation endpoint yet. Load the updated backend on your next restart.' : 'The explanation could not load. Your map is still available; try again.')
      }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [runId, lat, lon, question, attempt])
  const selectedSource = answer?.sources.find(item => item.id === source)
  const ask = (text: string) => {
    setLoading(true); setError(''); setAnswer(undefined); setSource(undefined)
    setQuestion(text); setAttempt(v => v + 1)
  }
  return <aside className="live-explanation" aria-labelledby="explanation-heading">
    <header><div><span className="eyebrow">Behind the prediction</span><h3 id="explanation-heading" tabIndex={-1} ref={heading}>Explain this location</h3></div>
      <button type="button" aria-label="Close explanation" onClick={onClose}>×</button></header>
    <div className="live-explanation-content">
      <div className="explanation-location"><strong>{selection.sample.value?.toFixed(2)} <small>RFU</small></strong><span>{selection.lat.toFixed(4)}° N · {Math.abs(selection.lon).toFixed(4)}° W</span>
        <p>Image acquired {new Date(selection.sample.acquired_at!).toLocaleString()}</p>
        <b>{selection.sample.outside_support ? 'Outside training support' : 'Within training ranges'}</b>
        <p>2025-trained estimate · seasonal transfer unvalidated</p></div>
      {selection.runId !== currentRunId && <p className="explanation-notice">The map has updated. This explanation stays with your selected snapshot; click the map again to inspect the new one.</p>}
      <div className="explanation-questions">{QUESTIONS.map(text => <button type="button" key={text} disabled={loading} onClick={() => ask(text)}>{text}</button>)}</div>
      <p className="explanation-question">{question}</p>
      {loading && <p role="status" className="explanation-notice">Reading this cell’s satellite evidence and scientific sources…</p>}
      {error && <div role="alert" className="explanation-notice"><p>{error}</p><button className="btn" onClick={() => ask(question)}>Try again</button></div>}
      {answer && <>
        <div className="explanation-mode">{answer.generation_mode.startsWith('gemini:') ? 'Gemini · grounded in cited evidence' : 'Evidence summary · AI unavailable'}</div>
        {answer.generation_mode === 'evidence' && answer.status === 'available' && <p className="explanation-notice">Showing recorded facts for this cell. A tailored answer to your question is unavailable.</p>}
        {answer.message && <p>{answer.message}</p>}
        <div aria-live="polite">{answer.paragraphs.map((paragraph, i) => <div className="explanation-paragraph" key={i}><p>{paragraph.text}</p>
          <div>{paragraph.source_ids.map(id => <button type="button" key={id} onClick={() => setSource(source === id ? undefined : id)} aria-pressed={source === id}>
            [{(answer.sources.findIndex(s => s.id === id) + 1)}] {answer.sources.find(s => s.id === id)?.title}
          </button>)}</div></div>)}</div>
        {selectedSource && <section className="explanation-source" aria-label="Citation evidence"><h4>{selectedSource.title}</h4>
          {selectedSource.metadata && <p>{[selectedSource.metadata.authors, selectedSource.metadata.year, selectedSource.metadata.section].filter(Boolean).join(' · ')}</p>}
          <pre>{selectedSource.text}</pre>
          {selectedSource.url && <a href={xrayResourceUrl(selectedSource.url)} target="_blank" rel="noreferrer">Open original source ↗</a>}
          {selectedSource.chunk_id && <small>RAG chunk: {selectedSource.chunk_id}</small>}
        </section>}
        <details className="explanation-limits"><summary>What this cannot tell us</summary><ul>{answer.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>
        <details className="explanation-limits"><summary>Evidence library · {answer.sources.length} sources</summary>
          {answer.sources.map((item, i) => <button type="button" key={item.id} onClick={() => setSource(item.id)}>[{i + 1}] {item.title}</button>)}
          <p>{answer.retrieval_status === 'bm25' ? 'Scientific passages retrieved from the existing RAG library by keyword relevance.' : 'Scientific library unavailable or no matching passages. Snapshot and packaged research evidence remain available.'}</p>
        </details>
      </>}
      <form onSubmit={event => { event.preventDefault(); if (draft.trim()) { ask(draft.trim()); setDraft('') } }}>
        <label htmlFor="satellite-question">Ask about this location</label>
        <textarea id="satellite-question" value={draft} maxLength={1000} rows={2} placeholder="Why might this patch be brighter?" onChange={event => setDraft(event.target.value)} />
        <button className="btn" disabled={loading || !draft.trim()}>Ask with evidence →</button>
      </form>
      <p className="explanation-footnote">Snapshot {selection.runId}. Explanations interpret evidence; they do not change the model prediction.</p>
    </div>
  </aside>
}
