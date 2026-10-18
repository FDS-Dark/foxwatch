import { api } from './api'
import type { XrayAnswer, XrayMetadata, XrayObservation, XraySegment, XrayStage } from '@/models/xray'

export async function fetchXrayMetadata(signal?: AbortSignal): Promise<XrayMetadata> {
  return (await api.get('/api/xray', { signal })).data
}

export async function fetchXraySurvey(signal?: AbortSignal): Promise<XrayObservation[]> {
  return (await api.get('/api/xray/survey', { signal })).data.observations
}

export async function fetchXraySegment(id: number, stage: XrayStage, signal?: AbortSignal): Promise<XraySegment> {
  return (await api.get(`/api/xray/segments/${id}`, { params: { stage }, signal })).data
}

export async function askXray(question: string, segmentId: number, signal?: AbortSignal): Promise<XrayAnswer> {
  return (await api.post('/api/xray/investigate', { question, segment_id: segmentId }, { signal })).data
}

export function xrayResourceUrl(path: string): string {
  return /^https?:/.test(path) ? path : `${api.defaults.baseURL || ''}${path}`
}
