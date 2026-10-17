import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from 'react'
import { DEMO_EVENT, DEMO_OBSERVATIONS, DEMO_SCENES, MAP_CENTER } from '../../data/demo/replay'
import type { EvidenceRecord, Observation, ObservationsMode, ReplayEvent, Scene } from '../../data/types/replay'

export interface ReplayDataState {
  event: ReplayEvent
  scenes: Scene[]
  scenesMode: string
  observations: Observation[]
  observationsMode: ObservationsMode
  mapCenter: [number, number]
  findEvidence: (id: string) => EvidenceRecord | null
}

const ReplayCtx = createContext<ReplayDataState | null>(null)

export function ReplayDataProvider({ children }: { children: ReactNode }) {
  const payload = useMemo(
    () => ({
      event: DEMO_EVENT,
      scenes: DEMO_SCENES,
      scenesMode: 'demo_fixture' as const,
      observations: DEMO_OBSERVATIONS,
      observationsMode: 'demo_fixture' as const,
      mapCenter: MAP_CENTER,
    }),
    [],
  )

  const findEvidence = useMemo(() => {
    return (id: string): EvidenceRecord | null => {
      const scene = payload.scenes.find((s) => s.evidence_id === id)
      if (scene) return { kind: 'scene', ...scene }
      const obs = payload.observations.find((o) => o.evidence_id === id)
      if (obs) return { kind: 'observation', ...obs }
      return null
    }
  }, [payload.observations, payload.scenes])

  const value = useMemo<ReplayDataState>(
    () => ({ findEvidence, ...payload }),
    [findEvidence, payload],
  )

  return <ReplayCtx.Provider value={value}>{children}</ReplayCtx.Provider>
}

export function useReplayData(): ReplayDataState {
  const ctx = useContext(ReplayCtx)
  if (!ctx) {
    throw new Error('useReplayData must be used within ReplayDataProvider')
  }
  return ctx
}
