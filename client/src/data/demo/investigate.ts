/** Cached investigate answers until investigator-api is wired in the UI. */

export const SUGGESTED_QUESTIONS = [
  'Why did the proxy rise between June 2 and June 7?',
  'Which scenes have quality limitations?',
  'What does the river gauge show around the rain event?',
]

export interface CachedAnswer {
  question: string
  answer: string
  evidence_ids: string[]
  limitations: string[]
}

export const CACHED_ANSWERS: CachedAnswer[] = [
  {
    question: SUGGESTED_QUESTIONS[0],
    answer:
      'Heavy rain on June 3–4 (24.6 mm, then 11.2 mm) preceded a rise in Fox River discharge that peaked at 9,100 ft³/s on June 5. The next clear scene, June 7, shows the NDCI proxy mean rising from 0.08 to 0.27. The timing is consistent with runoff-driven nutrient delivery, but this data alone cannot establish cause.',
    evidence_ids: [
      'noaa-usw00014898-prcp-2020-06-03',
      'noaa-usw00014898-prcp-2020-06-04',
      'usgs-04085059-q-2020-06-05',
      'scene-s2-20200602',
      'scene-s2-20200607',
    ],
    limitations: [
      'NDCI is a dimensionless spectral proxy, not a measured chlorophyll concentration.',
      'Correlation in timing does not demonstrate a causal runoff effect.',
    ],
  },
  {
    question: SUGGESTED_QUESTIONS[1],
    answer:
      'The June 5 scene has 62% cloud cover and is flagged cloud-limited, so its proxy value should not be compared directly with the clear scenes from June 2, 7, and 12.',
    evidence_ids: ['scene-s2-20200605'],
    limitations: ['Cloud masking removes pixels and can bias scene averages.'],
  },
  {
    question: SUGGESTED_QUESTIONS[2],
    answer:
      'Daily discharge at De Pere rose from 4,100 ft³/s on June 2 to a peak of 9,100 ft³/s on June 5, then receded. There is no reported value for June 7; the chart shows a gap instead of interpolating one.',
    evidence_ids: [
      'usgs-04085059-q-2020-06-02',
      'usgs-04085059-q-2020-06-05',
      'usgs-04085059-q-2020-06-07',
    ],
    limitations: ['The De Pere gauge reports daily values only.'],
  },
]
