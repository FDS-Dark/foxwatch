/**
 * Illustrative replay fixtures (June 2020 window).
 * Used when core-api has no USGS exports in data/downloads yet.
 */

import type { Observation, ReplayEvent, Scene } from '../types/replay'

export const DEMO_EVENT: ReplayEvent = {
  event_id: 'green_bay_candidate_window',
  title: 'Lower Green Bay water-color anomaly',
  place: 'Fox River mouth → Lower Green Bay, WI',
  start_date: '2020-06-01',
  end_date: '2020-06-14',
  event_claim_status: 'candidate',
}

export const MAP_CENTER: [number, number] = [44.585, -87.975]

export const DEMO_SCENES: Scene[] = [
  {
    scene_id: 'sentinel_scene_001',
    evidence_id: 'scene-s2-20200602',
    acquired_at_utc: '2020-06-02T16:50:00Z',
    cloud_cover_pct: 4,
    quality_flag: 'demo_fixture',
    proxy_name: 'NDCI',
    proxy_mean: 0.08,
    proxy_p90: 0.14,
    overlay_intensity: 0.25,
  },
  {
    scene_id: 'sentinel_scene_002',
    evidence_id: 'scene-s2-20200605',
    acquired_at_utc: '2020-06-05T16:40:00Z',
    cloud_cover_pct: 62,
    quality_flag: 'cloud_limited',
    proxy_name: 'NDCI',
    proxy_mean: 0.15,
    proxy_p90: 0.22,
    overlay_intensity: 0.45,
  },
  {
    scene_id: 'sentinel_scene_003',
    evidence_id: 'scene-s2-20200607',
    acquired_at_utc: '2020-06-07T16:50:00Z',
    cloud_cover_pct: 9,
    quality_flag: 'demo_fixture',
    proxy_name: 'NDCI',
    proxy_mean: 0.27,
    proxy_p90: 0.38,
    overlay_intensity: 0.9,
  },
  {
    scene_id: 'sentinel_scene_004',
    evidence_id: 'scene-s2-20200612',
    acquired_at_utc: '2020-06-12T16:50:00Z',
    cloud_cover_pct: 12,
    quality_flag: 'demo_fixture',
    proxy_name: 'NDCI',
    proxy_mean: 0.19,
    proxy_p90: 0.29,
    overlay_intensity: 0.6,
  },
]

export const BLOOM_SEEDS: { lat: number; lng: number; r: number; w: number }[] = [
  { lat: 44.548, lng: -88.0, r: 900, w: 1 },
  { lat: 44.562, lng: -87.985, r: 1400, w: 0.95 },
  { lat: 44.578, lng: -87.968, r: 1700, w: 0.85 },
  { lat: 44.595, lng: -87.952, r: 1900, w: 0.75 },
  { lat: 44.612, lng: -87.935, r: 1600, w: 0.6 },
  { lat: 44.6, lng: -87.99, r: 1200, w: 0.55 },
  { lat: 44.628, lng: -87.915, r: 1500, w: 0.45 },
  { lat: 44.585, lng: -88.005, r: 900, w: 0.5 },
]

const USGS_URL = 'https://waterdata.usgs.gov/monitoring-location/USGS-04085059/'
const NOAA_URL = 'https://www.ncei.noaa.gov/access/services/data/v1'

const DISCHARGE: (number | null)[] = [
  3900, 4100, 5200, 7800, 9100, 8600, null, 7200, 6400, 5900, 5300, 4900, 4700,
  4500,
]
const PRECIP: (number | null)[] = [
  0, 2.1, 24.6, 11.2, 0.4, 0, 0, null, 0, 1.3, 0, 0, 6.8, 0.2,
]

function dates(): string[] {
  const out: string[] = []
  const d = new Date(`${DEMO_EVENT.start_date}T00:00:00Z`)
  for (let i = 0; i < 14; i++) {
    out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

export const DEMO_OBSERVATIONS: Observation[] = dates().flatMap((date, i) => [
  {
    evidence_id: `usgs-04085059-q-${date}`,
    source: 'USGS',
    station_id: '04085059',
    metric: 'discharge',
    metric_code: '00060',
    observation_date: date,
    granularity: 'daily',
    value: DISCHARGE[i],
    unit: 'ft³/s',
    quality_flag: DISCHARGE[i] === null ? 'missing' : 'demo_fixture',
    source_url: USGS_URL,
  },
  {
    evidence_id: `noaa-usw00014898-prcp-${date}`,
    source: 'NOAA',
    station_id: 'USW00014898',
    metric: 'precipitation',
    observation_date: date,
    granularity: 'daily',
    value: PRECIP[i],
    unit: 'mm',
    quality_flag: PRECIP[i] === null ? 'missing' : 'demo_fixture',
    source_url: NOAA_URL,
  },
])
