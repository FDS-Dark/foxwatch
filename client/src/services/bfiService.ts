import { api } from '@/services/api'
import type { BfiAskResponse, BfiHealth, BfiInsightResponse } from '@/models/bfi'

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

export async function fetchBfiInsights(
  body: BfiInsightRequest,
  signal?: AbortSignal,
): Promise<BfiInsightResponse> {
  const { data } = await api.post<BfiInsightResponse>('/api/v1/bfi/insights', body, { signal })
  return data
}

export async function askBfiQuestion(
  question: string,
  options?: { use_live_data?: boolean; use_gemini?: boolean; signal?: AbortSignal },
): Promise<BfiAskResponse> {
  const { signal, ...body } = options ?? {}
  const { data } = await api.post<BfiAskResponse>(
    '/api/v1/bfi/ask',
    { question, use_live_data: body.use_live_data ?? true, use_gemini: body.use_gemini ?? true },
    { signal },
  )
  return data
}
