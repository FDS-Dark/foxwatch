import { api } from '@/services/api'
import type { ModelList, Prediction, RetrainJob } from '../data/types/review'

export async function fetchMlModels(): Promise<ModelList> {
  const { data } = await api.get<ModelList>('/api/v1/ml/models')
  return data
}

export async function fetchMlPredictions(sceneId: string): Promise<Prediction[]> {
  const { data } = await api.get<{ predictions: Prediction[] }>(
    '/api/v1/ml/predictions',
    { params: { scene_id: sceneId } },
  )
  return data.predictions
}

export async function runMlPredictionForReview(sceneId: string): Promise<Prediction> {
  const { data } = await api.post<{ prediction: Prediction }>(
    '/api/v1/ml/predictions/run',
    null,
    { params: { scene_id: sceneId } },
  )
  return data.prediction
}

export async function submitMlReview(
  predictionId: string,
  decision: 'approved' | 'denied',
  notes?: string,
): Promise<Prediction> {
  const { data } = await api.post<{ prediction: Prediction }>(
    `/api/v1/ml/predictions/${predictionId}/review`,
    { decision, notes },
  )
  return data.prediction
}

export async function retrainMlFromDenials(maxDenials = 5): Promise<RetrainJob> {
  const { data } = await api.post<RetrainJob>('/api/v1/ml/retrain', {
    max_denials: maxDenials,
  })
  return data
}

export type RollbackResult = {
  message: string
  active_model_version_id: string
  previous_active_model_version_id: string
}

export async function rollbackMlToBaseline(): Promise<RollbackResult> {
  const { data } = await api.post<RollbackResult>('/api/v1/ml/models/rollback')
  return data
}

export type ResetRetrainResult = RollbackResult & {
  removed_model_version_id: string
  restored_parent_model_version_id: string
}

export async function resetLatestMlRetrain(): Promise<ResetRetrainResult> {
  const { data } = await api.post<ResetRetrainResult>('/api/v1/ml/models/reset-retrain')
  return data
}
