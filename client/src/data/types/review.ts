export type PredictionClass = 'proxy_elevated' | 'proxy_normal'
export type ReviewDecision = 'approved' | 'denied'
export type PredictionReviewStatus = 'pending_review' | 'approved' | 'denied'

export interface ModelVersion {
  model_version_id: string
  name: string
  created_at_utc: string
  parent_model_version_id: string | null
  training_job_id: string | null
  artifact_uri: string | null
  parameters_json: Record<string, unknown>
  training_summary: Record<string, unknown>
  disclaimer: string
}

export interface ModelList {
  active_model_version_id: string
  models: ModelVersion[]
}

export interface Prediction {
  prediction_id: string
  scene_id: string
  event_id: string
  model_version_id: string
  predicted_class: PredictionClass
  score: number
  feature_snapshot: Record<string, unknown>
  review_status: PredictionReviewStatus
  review_decision: ReviewDecision | null
  reviewed_at_utc: string | null
  reviewer_notes: string | null
  used_in_training_job_id: string | null
  created_at_utc: string
}

export interface RetrainJob {
  training_job_id: string
  status: string
  parent_model_version_id: string
  new_model_version_id: string | null
  denial_sample_ids: string[]
  message: string | null
}

