import { api } from '@/services/api'
import type { LatestObservations } from '@/models/observations'

export async function fetchLatestObservations(signal?: AbortSignal): Promise<LatestObservations> {
  const { data } = await api.get<LatestObservations>('/api/observations/latest', {
    signal,
    headers: { 'Cache-Control': 'no-store' },
  })
  if (data.source !== 'tiger_data' || !Array.isArray(data.readings)) {
    throw new Error('Unexpected observation response')
  }
  return data
}
