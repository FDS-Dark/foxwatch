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
      title?: string
      chapter?: string
      section?: string
      authors?: string
      year?: string | number
      /** Legacy / Gemini free-text citation */
      citation?: string
    }>
    generation_mode?: string
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
}
