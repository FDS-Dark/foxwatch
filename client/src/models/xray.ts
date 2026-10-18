export type XrayStage = 'hidden' | 'location' | 'satellite' | 'reveal'
export type XrayModel = 'rf_xy' | 'gp_xy' | 'idw' | 'rf_xysat' | 'gp_resid'
export type SatelliteModel = 'gp_resid' | 'rf_xysat'
export type XrayPosition = { id: number; lat: number; lon: number; observed_at: string }
export type XrayObservation = XrayPosition & {
  along_m: number; segment: number; value: number; raw_samples: number
}
export type XrayPoint = XrayPosition & {
  distance_km: number; scene_id: string; lag_hours: number
  value?: number; predictions?: Partial<Record<XrayModel, number>>
}
export type XraySource = { id: string; title: string; url: string }
export type XrayLayer = {
  id: string; title: string; units: string; scope: string; url: string
  bounds: [[number, number], [number, number]]
  display_min: number; display_max: number; acquired_at: string; scene_id: string
}
export type XrayMetadata = {
  campaign: string; units: string; variable: string; model_version: string
  aggregation: string; protocol: string; start: string; end: string
  observation_count: number; models: Record<XrayModel, string>
  cases: { id: number; label: string; matched_count: number; total_count: number }[]
  scenes: { id: string; acquired_at: string }[]
  sources: XraySource[]; limitations: string[]; layers: XrayLayer[]
  bay?: {
    layers: XrayLayer[]; extrapolation: XrayLayer; satellite?: XrayLayer
    training_bins: number; resolution_m: number; valid_cells: number; extrapolated_cells: number; note: string
    scenes?: { id: string; acquired_at: string; url: string }[]
  }
  overall: {
    folds: number; test_bins: number
    primary_comparison: { pooled_MAE_change_pct: number; fold_bootstrap_95ci_pct: number[] }
    diagnostic_comparison: { folds_worse: number }
  }
}
export type XraySegment = {
  id: number; label: string; stage: XrayStage; protocol: string; units: string
  matched_count: number; total_count: number
  training: XrayObservation[]; target: XrayPosition[]; points: XrayPoint[]
  metrics?: Record<XrayModel, { mae: number; bias: number; rmse: number }>
  surfaces?: {
    layers: Partial<Record<XrayModel, XrayLayer>>
    extrapolation?: XrayLayer
    resolution_m: number; support_radius_m: number; note: string
  }
}
export type XrayAnswer = {
  supported: boolean; answer: string[]; sources: XraySource[]; limitations: string[]; mode: string
}
