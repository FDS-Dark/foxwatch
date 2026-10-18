import { api } from './api'
import type { XrayAnswer, XrayMetadata, XrayObservation, XraySegment, XrayStage } from '@/models/xray'
import type { LiveExplanation, LiveSample, LiveXray } from '@/models/xrayLive'

export async function fetchLiveXray(signal?: AbortSignal): Promise<LiveXray> {
  return (await api.get('/api/xray/live', { signal, headers: { 'Cache-Control': 'no-store' } })).data
}

export async function fetchLiveSample(runId: string, lat: number, lon: number, signal?: AbortSignal): Promise<LiveSample> {
  return (await api.get(`/api/xray/live/${runId}/sample`, { params: { lat, lon }, signal })).data
}

export async function explainLivePoint(runId: string, lat: number, lon: number, question: string, signal?: AbortSignal): Promise<LiveExplanation> {
  return (await api.post(`/api/xray/live/${runId}/explain`, { lat, lon, question }, { signal, timeout: 60_000 })).data
}

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
