export interface BfiHealth {
  status: string
  gemini_configured: boolean
}

export interface BfiAskResponse {
  question: string
  answer: string
  generation_mode: string
  limitations: string[]
  supporting_chunks: BfiInsightResponse['evidence']['supporting_chunks']
  bfi: {
    classification: string
    score: number
    max_possible_score: number
  }
}

export interface BfiInsightResponse {
  bfi: {
    classification: string
    score: number
    max_possible_score: number
    favorability_percent?: number
    drivers: string[]
    factors?: Array<Record<string, unknown>>
    reasons?: string[]
  }
  insights: {
    executive_summary: string
    bloom_assessment?: string
    key_contributing_factors: string[]
    scientific_interpretation: string
    confidence: { level: string; percent: number; reason: string }
    sources: Array<{
      name: string
      organization: string
      summary: string
      url?: string
      source_origin?: string
      consistency?: 'aligned' | 'partial' | 'unverified'
      evidence_indices: number[]
      backing_publications?: Array<{
        title: string
        authors?: string
        year?: string | number
        section?: string
      }>
    }>
    generation_mode?: string
    rag_grounded?: boolean
  }
  evidence: {
    context_summary: string
    retrieval_tags: string[]
    supporting_chunks: Array<{
      chunk_id: string
      retrieval_summary: string
      text: string
      tags: string[]
      matched_tags: string[]
      hybrid_score?: number
      metadata: {
        document_title: string
        chapter: string
        section: string
        authors: string
        year: string | number
        source_type: string
      }
    }>
  }
  gemini_status?: string
  source_discovery_mode?: string
  inputs?: Record<string, unknown>
  inputs_provenance?: {
    source: string
    as_of?: string
    seasonal_median_streamflow_cfs?: number
    solar_radiation_level?: string
    solar_radiation_note?: string
    station_readings?: Array<{
      bfi_field: string
      parameter_code: string
      value: number | null
      unit?: string | null
      observed_at?: string
      used_fallback?: boolean
    }>
  }
}
