export type LabelTaxonomy =
  | 'proxy_elevated_plausible'
  | 'proxy_elevated_rejected'
  | 'uncertain_quality'
  | 'context_only'

export type LabelConfidence = 'low' | 'medium' | 'high'
export type LabelStatus = 'draft' | 'published' | 'superseded'

export interface HumanLabel {
  label_id: string
  event_id: string
  scene_id: string
  source_run_id: string
  taxonomy: LabelTaxonomy
  confidence: LabelConfidence
  notes: string | null
  status: LabelStatus
  created_at_utc: string
  created_by: string
  supersedes_label_id: string | null
  disclaimer: string
}

export interface HumanLabelCreate {
  event_id: string
  source_run_id: string
  taxonomy: LabelTaxonomy
  confidence?: LabelConfidence
  notes?: string
  status?: LabelStatus
  created_by?: string
}

export interface AnalysisRun {
  run_id: string
  event_id: string
  method: string
  parameters_json: Record<string, unknown>
  created_at_utc: string
  manifest_sha256: string | null
  parent_run_id: string | null
}

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

export interface RerunJobResponse {
  job_id: string
  status: string
  event_id: string
  parent_run_id: string
  run_id: string | null
  message: string | null
}
