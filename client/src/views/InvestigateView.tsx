import { useState, type FormEvent } from 'react'
import { useOpenEvidence } from '../components/EvidenceContext'
import {
  CACHED_ANSWERS,
  SUGGESTED_QUESTIONS,
  type CachedAnswer,
} from '../data/demo/investigate'
import { useReplayData } from '../features/replay/ReplayDataContext'

type Turn = { id: number; question: string; answer: CachedAnswer | null }

export function InvestigateView() {
  const { findEvidence } = useReplayData()
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const openEvidence = useOpenEvidence()

  function evidenceLabel(id: string) {
    const rec = findEvidence(id)
    if (!rec) return id
    if (rec.kind === 'scene') return `Scene · ${rec.acquired_at_utc.slice(5, 10)}`
    const date = rec.observation_date?.slice(5) ?? '—'
    return rec.metric === 'discharge' ? `USGS flow · ${date}` : `NOAA rain · ${date}`
  }

  function ask(question: string) {
    const q = question.trim()
    if (!q) return
    const answer = CACHED_ANSWERS.find((a) => a.question === q) ?? null
    setTurns((t) => [...t, { id: Date.now(), question: q, answer }])
    setDraft('')
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    ask(draft)
  }

  return (
    <div className="investigate">
      <section className="card investigate__chat" aria-labelledby="inv-title">
        <header className="card__header">
          <div>
            <h2 id="inv-title" className="card__title">
              Ask the investigator
            </h2>
            <p className="card__sub">
              Answers use only retrieved records. Every claim links to its
              source.
            </p>
          </div>
          <span className="chip chip--cached">Cached mode</span>
        </header>

        <ol className="thread" aria-live="polite">
          {turns.length === 0 ? (
            <li className="thread__empty">
              <p>Start with a suggested question, or write your own.</p>
            </li>
          ) : null}
          {turns.map((t) => (
            <li key={t.id} className="thread__turn">
              <p className="bubble bubble--user">{t.question}</p>
              {t.answer ? (
                <div className="bubble bubble--agent">
                  <p>{t.answer.answer}</p>
                  <div className="cites" aria-label="Cited evidence">
                    {t.answer.evidence_ids.map((id) => (
                      <button
                        key={id}
                        type="button"
                        className="cite"
                        onClick={() => openEvidence(id)}
                      >
                        {evidenceLabel(id)}
                      </button>
                    ))}
                  </div>
                  <ul className="limits">
                    {t.answer.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="bubble bubble--agent bubble--muted">
                  <p>
                    The live investigator isn't connected yet, and no cached
                    answer exists for this question. FoxWatch won't make up an
                    answer without evidence.
                  </p>
                </div>
              )}
            </li>
          ))}
        </ol>

        <form className="composer" onSubmit={onSubmit}>
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about this event…"
            autoComplete="off"
          />
          <button type="submit" className="btn btn--primary" disabled={!draft.trim()}>
            Ask
          </button>
        </form>
      </section>

      <aside className="investigate__side">
        <section className="card" aria-labelledby="suggest-title">
          <h2 id="suggest-title" className="card__title">
            Suggested questions
          </h2>
          <ul className="suggestions">
            {SUGGESTED_QUESTIONS.map((q) => (
              <li key={q}>
                <button type="button" className="suggestion" onClick={() => ask(q)}>
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="card card--tint" aria-labelledby="rules-title">
          <h2 id="rules-title" className="card__title">
            How answers stay honest
          </h2>
          <ul className="rules">
            <li>Citations must resolve to stored records, or the claim is removed.</li>
            <li>Proxies are never reported as chlorophyll concentrations.</li>
            <li>Timing correlation is not presented as cause.</li>
            <li>Only published analyst labels can be cited.</li>
          </ul>
        </section>
      </aside>
    </div>
  )
}
