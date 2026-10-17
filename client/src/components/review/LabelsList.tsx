import { useEffect, useState } from 'react'
import type { HumanLabel } from '../../data/types/review'

type Props = {
  labels: HumanLabel[]
  refreshKey: number
}

export function LabelsList({ labels, refreshKey }: Props) {
  const [local, setLocal] = useState(labels)

  useEffect(() => {
    setLocal(labels)
  }, [labels, refreshKey])

  if (local.length === 0) {
    return (
      <section className="panel panel--compact">
        <h2>Published labels</h2>
        <p className="muted">No labels yet for this event.</p>
      </section>
    )
  }

  return (
    <section className="panel panel--compact">
      <h2>Published labels</h2>
      <ul className="label-list">
        {local.map((label) => (
          <li key={label.label_id}>
            <code>{label.label_id}</code>
            <span className="tag">{label.taxonomy}</span>
            <time dateTime={label.created_at_utc}>
              {label.created_at_utc.slice(0, 19)}Z
            </time>
            {label.notes ? <p>{label.notes}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
