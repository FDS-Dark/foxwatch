import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { EvidenceRecord } from '../data/types/replay'
import { useReplayData } from '../features/replay/ReplayDataContext'
import { FixtureBadge } from './FixtureBadge'

const EvidenceCtx = createContext<(id: string) => void>(() => {})

export const useOpenEvidence = () => useContext(EvidenceCtx)

function EvidenceDialog({
  resolveEvidence,
  children,
}: {
  resolveEvidence: (id: string) => EvidenceRecord | null
  children: ReactNode
}) {
  const [record, setRecord] = useState<EvidenceRecord | null>(null)
  const [missingId, setMissingId] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)

  const open = useCallback((id: string) => {
    const found = resolveEvidence(id)
    setRecord(found)
    setMissingId(found ? null : id)
    dialogRef.current?.showModal()
  }, [resolveEvidence])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const onClick = (e: MouseEvent) => {
      if (e.target === dialog) dialog.close()
    }
    dialog.addEventListener('click', onClick)
    return () => dialog.removeEventListener('click', onClick)
  }, [])

  return (
    <EvidenceCtx.Provider value={open}>
      {children}
      <dialog
        ref={dialogRef}
        className="evidence"
        aria-labelledby="evidence-title"
      >
        <div className="evidence__inner">
          <header className="evidence__header">
            <p className="eyebrow">Evidence record</p>
            <h2 id="evidence-title">
              {record?.kind === 'scene'
                ? 'Sentinel-2 L2A scene'
                : record?.kind === 'observation'
                  ? `${record.source} ${record.metric}`
                  : 'Unknown evidence'}
            </h2>
            <button
              type="button"
              className="icon-btn"
              onClick={() => dialogRef.current?.close()}
              aria-label="Close evidence"
            >
              ×
            </button>
          </header>

          {missingId ? (
            <p>
              No record exists for <code>{missingId}</code>. FoxWatch only shows
              evidence that resolves to a stored source row.
            </p>
          ) : null}

          {record ? (
            <>
              <dl className="evidence__grid">
                <Field label="Evidence ID" mono value={record.evidence_id} />
                {record.kind === 'scene' ? (
                  <>
                    <Field
                      label="Acquired (UTC)"
                      value={record.acquired_at_utc.replace('T', ' ').slice(0, 16)}
                    />
                    <Field label="Proxy" value={`${record.proxy_name} (dimensionless)`} />
                    <Field label="Proxy mean" value={record.proxy_mean.toFixed(2)} />
                    <Field label="Proxy p90" value={record.proxy_p90.toFixed(2)} />
                    <Field label="Cloud cover" value={`${record.cloud_cover_pct}%`} />
                    <Field label="Quality" value={record.quality_flag.replace('_', ' ')} />
                  </>
                ) : (
                  <>
                    <Field label="Station" value={record.station_id} />
                    <Field label="Date (local)" value={record.observation_date} />
                    <Field label="Cadence" value={record.granularity} />
                    <Field
                      label="Value"
                      value={
                        record.value === null
                          ? 'Not reported'
                          : `${record.value.toLocaleString()} ${record.unit}`
                      }
                    />
                    <Field label="Quality" value={record.quality_flag.replace('_', ' ')} />
                  </>
                )}
              </dl>
              <div className="evidence__footer">
                <FixtureBadge />
                {record.kind === 'observation' ? (
                  <a href={record.source_url} target="_blank" rel="noreferrer">
                    View source ↗
                  </a>
                ) : (
                  <a
                    href="https://dataspace.copernicus.eu/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Copernicus Data Space ↗
                  </a>
                )}
              </div>
            </>
          ) : null}
        </div>
      </dialog>
    </EvidenceCtx.Provider>
  )
}

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const { findEvidence } = useReplayData()
  return (
    <EvidenceDialog resolveEvidence={findEvidence}>{children}</EvidenceDialog>
  )
}

function Field({
  label,
  value,
  mono,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={mono ? 'mono' : undefined}>{value}</dd>
    </div>
  )
}
