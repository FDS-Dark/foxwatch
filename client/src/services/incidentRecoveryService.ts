import { api } from '@/services/api'
import type { IncidentRecoveryRequest, IncidentRecoveryResponse } from '@/models/incidentRecovery'

export async function fetchIncidentRecovery(
  body: IncidentRecoveryRequest = {},
  options?: { signal?: AbortSignal },
): Promise<IncidentRecoveryResponse> {
  const { data } = await api.post<IncidentRecoveryResponse>(
    '/api/v1/incident-recovery/suggest',
    { use_gemini: true, top_k: 8, ...body },
    { signal: options?.signal },
  )
  return data
}
