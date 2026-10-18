import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parsePrediction, predictionBucket } from '../src/data/types/prediction'

test('classifies exact boundaries using the unrounded probability', () => {
  for (const [value, expected] of [[0, 'low'], [0.49999, 'low'], [0.5, 'medium'], [0.79999, 'medium'], [0.8, 'high'], [1, 'high']] as const) {
    assert.equal(predictionBucket(value), expected)
  }
})

test('rejects invalid model scores instead of showing a risk bucket', () => {
  for (const value of [-0.01, 1.01, NaN, Infinity]) assert.throws(() => predictionBucket(value))
  assert.throws(() => parsePrediction({ source: 'tiger_data', station_id: 'test', inputs: [], status: 'available', algal_bloom: 1 }))
})

test('uses probability rather than the binary classification and supports missing data', () => {
  const result = parsePrediction({ source: 'tiger_data', station_id: 'test', inputs: [], status: 'available', probability: 0.65, algal_bloom: 1 })
  assert.equal(result.status === 'available' && predictionBucket(result.probability), 'medium')
  assert.equal(parsePrediction({ source: 'tiger_data', station_id: 'test', inputs: [], status: 'unavailable', missing_features: ['discharge_mean'] }).status, 'unavailable')
})
