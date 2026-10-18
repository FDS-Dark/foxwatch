import { api } from '@/services/api'
import type { BfiHealth, BfiInsightResponse } from '@/models/bfi'

export type BfiInsightRequest = {
  water_temperature_c?: number
  phosphorus_ug_l?: number
  nitrogen_mg_l?: number
  streamflow_cfs?: number
  seasonal_median_streamflow_cfs?: number
  rainfall_7day_in?: number
  solar_radiation_level?: string
  use_live_data?: boolean
  use_gemini?: boolean
}

export async function fetchBfiHealth(): Promise<BfiHealth> {
  const { data } = await api.get<BfiHealth>('/api/health')
  return data
}

export async function fetchBfiInsights(body: BfiInsightRequest): Promise<BfiInsightResponse> {
  const { data } = await api.post<BfiInsightResponse>('/api/v1/bfi/insights', body)
  return data
}
