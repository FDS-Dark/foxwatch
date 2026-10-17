import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { Scene } from '../data/types/replay'
import { useReplayData } from '../features/replay/ReplayDataContext'
import { formatDay } from '../lib/format'

const DAY = 86_400_000

type Props = {
  scenes: Scene[]
  index: number
  onChange: (index: number) => void
}

export function SceneTimeline({ scenes, index, onChange }: Props) {
  const { event, observations } = useReplayData()
  const start = Date.parse(`${event.start_date}T00:00:00Z`)
  const end = Date.parse(`${event.end_date}T23:59:59Z`)
  const pct = (iso: string) => ((Date.parse(iso) - start) / (end - start)) * 100

  const [playing, setPlaying] = useState(false)
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => {
      onChange((index + 1) % scenes.length)
    }, 1800)
    return () => window.clearInterval(id)
  }, [playing, index, scenes.length, onChange])

  const rain = observations.filter((o) => o.metric === 'precipitation')
  const maxRain = Math.max(1, ...rain.map((r) => r.value ?? 0))

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    let next = index
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = index + 1
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = index - 1
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = scenes.length - 1
    else return
    e.preventDefault()
    next = (next + scenes.length) % scenes.length
    onChange(next)
    refs.current[next]?.focus()
  }

  const days = Math.round((end - start) / DAY)

  return (
    <div className="timeline">
      <button
        type="button"
        className="timeline__play"
        onClick={() => setPlaying((p) => !p)}
        aria-pressed={playing}
        aria-label={playing ? 'Pause replay' : 'Play replay'}
      >
        {playing ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 5v14l12-7z" />
          </svg>
        )}
      </button>

      <div className="timeline__track-wrap">
        <div className="timeline__rain" aria-hidden="true">
          {rain.map((r) => (
            <span
              key={r.evidence_id}
              className={r.value === null ? 'rain rain--missing' : 'rain'}
              style={{
                left: `${pct(`${r.observation_date}T12:00:00Z`)}%`,
                height:
                  r.value === null ? '100%' : `${(r.value / maxRain) * 100}%`,
                width: `${100 / (days + 1) - 1}%`,
              }}
            />
          ))}
        </div>
        <div className="timeline__track" aria-hidden="true">
          <span
            className="timeline__fill"
            style={{ width: `${pct(scenes[index].acquired_at_utc)}%` }}
          />
        </div>
        <div
          className="timeline__scenes"
          role="radiogroup"
          aria-label="Satellite acquisition dates"
          onKeyDown={onKey}
        >
          {scenes.map((s, i) => (
            <button
              key={s.scene_id}
              ref={(el) => {
                refs.current[i] = el
              }}
              type="button"
              role="radio"
              aria-checked={i === index}
              tabIndex={i === index ? 0 : -1}
              className={`timeline__scene${
                s.quality_flag === 'cloud_limited' ? ' is-cloudy' : ''
              }`}
              style={{ left: `${pct(s.acquired_at_utc)}%` }}
              onClick={() => onChange(i)}
              aria-label={`${formatDay(s.acquired_at_utc)}${
                s.quality_flag === 'cloud_limited'
                  ? `, cloud limited (${s.cloud_cover_pct}% cloud)`
                  : ''
              }`}
            >
              <span className="timeline__dot" aria-hidden="true" />
              <span className="timeline__date">
                {formatDay(s.acquired_at_utc)}
              </span>
            </button>
          ))}
        </div>
        <div className="timeline__ends" aria-hidden="true">
          <span>{formatDay(`${event.start_date}T00:00:00Z`)}</span>
          <span className="timeline__legend">
            <span className="rain-swatch" /> daily rain (NOAA)
          </span>
          <span>{formatDay(`${event.end_date}T00:00:00Z`)}</span>
        </div>
      </div>
    </div>
  )
}
