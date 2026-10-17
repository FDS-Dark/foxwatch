/**
 * In-browser demo store for Review & retrain (no backend).
 */

import { DEMO_EVENT_ID, DEMO_PARENT_RUN_ID } from '../../config/demo'
import type {
  AnalysisRun,
  HumanLabel,
  HumanLabelCreate,
  ModelList,
  Prediction,
  RetrainJob,
  RerunJobResponse,
  ReviewDecision,
} from '../types/review'

const ACTIVE = 'mv_v1_baseline_demo'

let labels: HumanLabel[] = []
let predictions: Prediction[] = []
let runs: AnalysisRun[] = [
  {
    run_id: DEMO_PARENT_RUN_ID,
    event_id: DEMO_EVENT_ID,
    method: 'NDCI_dimensionless_v1',
    parameters_json: { index: 'NDCI', cloud_mask: 's2_l2a_qa' },
    created_at_utc: '2026-10-17T14:00:00Z',
    manifest_sha256: null,
    parent_run_id: null,
  },
]

let models: ModelList = {
  active_model_version_id: ACTIVE,
  models: [
    {
      model_version_id: ACTIVE,
      name: 'proxy_classifier_baseline',
      created_at_utc: '2026-10-17T12:00:00Z',
      parent_model_version_id: null,
      training_job_id: null,
      artifact_uri: null,
      parameters_json: { elevated_bias: 0.52, threshold: 0.5 },
      training_summary: { note: 'Frontend demo only' },
      disclaimer: 'Unvalidated proxy scores for UI demo.',
    },
  ],
}

function uid(prefix: string) {
  return `${prefix}-${crypto.randomUUID().slice(0, 8)}`
}

function nowUtc() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
}

export function listEventLabels(eventId: string): HumanLabel[] {
  return labels.filter((l) => l.event_id === eventId)
}

export function createSceneLabel(
  sceneId: string,
  body: HumanLabelCreate,
): HumanLabel {
  const label: HumanLabel = {
    label_id: uid('hl'),
    event_id: body.event_id,
    scene_id: sceneId,
    source_run_id: body.source_run_id,
    taxonomy: body.taxonomy,
    confidence: body.confidence ?? 'medium',
    notes: body.notes?.trim() || null,
    status: body.status ?? 'published',
    created_at_utc: nowUtc(),
    created_by: body.created_by ?? 'analyst_demo',
    supersedes_label_id: null,
    disclaimer: 'Analyst judgment; not lab-confirmed HAB detection.',
  }
  labels = [...labels, label]
  return label
}

export function listModels(): ModelList {
  return structuredClone(models)
}

export function listScenePredictions(sceneId: string): Prediction[] {
  return predictions.filter((p) => p.scene_id === sceneId)
}

export function createPrediction(sceneId: string): Prediction {
  const active = models.models.find(
    (m) => m.model_version_id === models.active_model_version_id,
  )
  const bias = Number(active?.parameters_json.elevated_bias ?? 0.5)
  const threshold = Number(active?.parameters_json.threshold ?? 0.5)
  const score = Math.min(0.99, Math.max(0.05, bias + 0.08 * Math.random()))
  const elevated = score >= threshold
  const prediction: Prediction = {
    prediction_id: uid('pred'),
    scene_id: sceneId,
    event_id: DEMO_EVENT_ID,
    model_version_id: models.active_model_version_id,
    predicted_class: elevated ? 'proxy_elevated' : 'proxy_normal',
    score,
    feature_snapshot: { demo: true },
    review_status: 'pending_review',
    review_decision: null,
    reviewed_at_utc: null,
    reviewer_notes: null,
    used_in_training_job_id: null,
    created_at_utc: nowUtc(),
  }
  predictions = [...predictions, prediction]
  return prediction
}

export function reviewPrediction(
  predictionId: string,
  decision: ReviewDecision,
  notes?: string,
): Prediction {
  const idx = predictions.findIndex((p) => p.prediction_id === predictionId)
  if (idx < 0) throw new Error('Prediction not found')
  const updated: Prediction = {
    ...predictions[idx],
    review_status: decision,
    review_decision: decision,
    reviewed_at_utc: nowUtc(),
    reviewer_notes: notes?.trim() || null,
  }
  predictions = predictions.map((p, i) => (i === idx ? updated : p))
  return updated
}

export function retrainModel(maxDenials = 1): RetrainJob {
  const denials = predictions.filter(
    (p) => p.review_status === 'denied' && !p.used_in_training_job_id,
  )
  const batch = denials.slice(0, maxDenials)
  if (batch.length === 0) {
    throw new Error('No denied predictions available for retrain')
  }
  const parent = models.active_model_version_id
  const parentModel = models.models.find((m) => m.model_version_id === parent)!
  const newId = uid('mv')
  const tjob = uid('tjob')
  const threshold = Number(parentModel.parameters_json.threshold ?? 0.5) + 0.015
  const bias = Number(parentModel.parameters_json.elevated_bias ?? 0.5) - 0.03
  models = {
    active_model_version_id: newId,
    models: [
      ...models.models,
      {
        model_version_id: newId,
        name: 'proxy_classifier_retrained_demo',
        created_at_utc: nowUtc(),
        parent_model_version_id: parent,
        training_job_id: tjob,
        artifact_uri: null,
        parameters_json: { elevated_bias: bias, threshold },
        training_summary: { denial_count: batch.length, demo: true },
        disclaimer: parentModel.disclaimer,
      },
    ],
  }
  predictions = predictions.map((p) =>
    batch.some((d) => d.prediction_id === p.prediction_id)
      ? { ...p, used_in_training_job_id: tjob }
      : p,
  )
  return {
    training_job_id: tjob,
    status: 'completed',
    parent_model_version_id: parent,
    new_model_version_id: newId,
    denial_sample_ids: batch.map((p) => p.prediction_id),
    message: null,
  }
}

export function listAnalysisRuns(eventId: string): AnalysisRun[] {
  return runs.filter((r) => r.event_id === eventId)
}

export function triggerHumanInformedRerun(
  eventId: string,
  body: { parent_run_id: string; adjustment?: string },
): RerunJobResponse {
  const published = labels.filter((l) => l.status === 'published')
  if (published.length === 0) {
    return {
      job_id: uid('job'),
      status: 'failed',
      event_id: eventId,
      parent_run_id: body.parent_run_id,
      run_id: null,
      message: 'Publish at least one label before re-run.',
    }
  }
  const runId = uid('run_v2_human_informed')
  runs = [
    ...runs,
    {
      run_id: runId,
      event_id: eventId,
      method: 'NDCI_dimensionless_v1_human_informed',
      parameters_json: {
        parent_run_id: body.parent_run_id,
        human_label_ids: published.map((l) => l.label_id),
        adjustment: body.adjustment ?? 'threshold_recalibration_v1',
      },
      created_at_utc: nowUtc(),
      manifest_sha256: 'demo_manifest_sha256',
      parent_run_id: body.parent_run_id,
    },
  ]
  return {
    job_id: uid('job'),
    status: 'completed',
    event_id: eventId,
    parent_run_id: body.parent_run_id,
    run_id: runId,
    message: `Created ${runId} (frontend demo).`,
  }
}
