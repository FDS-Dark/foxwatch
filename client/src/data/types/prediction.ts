export interface PredictionInput {
  feature: string
  parameter_code: string
  value: number
  observed_at: string
  used_fallback: boolean
}

export type BloomPrediction = {
  source: 'tiger_data'
  station_id: string
  inputs: PredictionInput[]
} & ({
  status: 'available'
  probability: number
} | {
  status: 'unavailable'
  missing_features: string[]
})

export function predictionBucket(probability: number): 'low' | 'medium' | 'high' {
  if (!Number.isFinite(probability) || probability < 0 || probability > 1) {
    throw new Error('Prediction probability must be between 0 and 1')
  }
  return probability < 0.5 ? 'low' : probability < 0.8 ? 'medium' : 'high'
}

export function parsePrediction(value: unknown): BloomPrediction {
  if (!value || typeof value !== 'object') throw new Error('Invalid prediction')
  const result = value as BloomPrediction
  if (result.source !== 'tiger_data' || typeof result.station_id !== 'string' || !Array.isArray(result.inputs)) {
    throw new Error('Invalid prediction source')
  }
  if (result.status === 'available') {
    if (typeof result.probability !== 'number') throw new Error('Missing probability')
    predictionBucket(result.probability)
  } else if (result.status !== 'unavailable' || !Array.isArray(result.missing_features)) {
    throw new Error('Invalid prediction status')
  }
  return result
}
