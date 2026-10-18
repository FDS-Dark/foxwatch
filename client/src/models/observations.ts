export interface ObservationReading {
  parameter_code: string
  time_series_id: string
  observed_at: string
  value: number | null
  unit: string | null
  approval_status: string | null
  qualifier: string | null
  ingested_at: string
}

export interface LatestObservations {
  source: 'tiger_data'
  station_id: string
  requested_parameters: string[]
  readings: ObservationReading[]
  missing_parameters: string[]
  fetched_at: string
  stale_after_seconds: number
}
