export type QualityFlag =
  | 'good'
  | 'cloud_limited'
  | 'demo_fixture'
  | 'missing'
  | string

export interface Scene {
  scene_id: string
  evidence_id: string
  acquired_at_utc: string
  cloud_cover_pct: number
  quality_flag: QualityFlag
  proxy_name: string
  proxy_mean: number
  proxy_p90: number
  overlay_intensity: number
}

export interface Observation {
  evidence_id: string
  source: 'USGS' | 'NOAA' | string
  station_id: string
  metric: string
  metric_code?: string
  metric_label?: string
  observation_date: string | null
  observed_at?: string | null
  granularity: 'daily' | 'instantaneous' | string
  value: number | null
  unit: string
  quality_flag: QualityFlag
  source_url: string
}

export interface ReplayEvent {
  event_id: string
  title: string
  place: string
  start_date: string
  end_date: string
  event_claim_status: 'candidate' | 'documented' | string
}

export type ObservationsMode = 'usgs_exports' | 'demo_fixture' | 'none'

export interface ReplayTimeline extends ReplayEvent {
  status: string
  scenes: Scene[]
  scenes_mode: 'demo_fixture' | string
  observations: Observation[]
  observations_mode: ObservationsMode
  observations_sources?: string[]
  map_center?: [number, number]
  disclaimers?: string[]
}

export type EvidenceRecord =
  | ({ kind: 'scene' } & Scene)
  | ({ kind: 'observation' } & Observation)
