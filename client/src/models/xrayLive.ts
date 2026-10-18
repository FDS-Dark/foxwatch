import type { XrayLayer } from './xray'

export type LiveSnapshot = {
  run_id: string; generated_at: string; catalog_checked_at: string; acquisition_start: string; acquisition_end: string
  source: string; layers: XrayLayer[]; resolution_m: number; valid_cells: number; modeled_area_km2: number
  training_bins: number; training_period: string; model: string; note: string; max_scene_age_days: number
  extrapolated_cells: number; outside_feature_range_cells: number
  scenes: { id: string; acquired_at: string; modeled_cells: number; url: string }[]
  statistics: { p10: number; median: number; p90: number }
  region?: { name: string; definition: string; source_url: string; bounds: XrayLayer['bounds'] }
}
export type LiveXray = {
  status: 'ready' | 'stale' | 'unavailable'; server_time: string
  refresh: { phase: string; message: string; checked_at: string | null; catalog_checked_at?: string; overdue: boolean }
  map: LiveSnapshot | null; newest_image_age_hours?: number; oldest_image_age_hours?: number
}
export type LiveSample = {
  status: 'available' | 'outside' | 'masked'; lat: number; lon: number; value?: number
  acquired_at?: string; scene_id?: string; outside_support?: boolean
}
