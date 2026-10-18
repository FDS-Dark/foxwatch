import { api } from '@/services/api'
import { parsePrediction, type BloomPrediction } from '@/models/prediction'

export async function fetchLatestPrediction(signal?: AbortSignal): Promise<BloomPrediction> {
  const { data } = await api.get<unknown>('/api/predictions/latest', {
    signal,
    headers: { 'Cache-Control': 'no-store' },
  })
  return parsePrediction(data)
}
