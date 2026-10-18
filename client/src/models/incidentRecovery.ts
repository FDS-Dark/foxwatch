export type RecoveryPriority = 'immediate' | 'short_term' | 'long_term'
export type SuggestionCategory = 'algae_cleanup' | 'consequence_reduction'

export type RecoverySourceCitation = {
  chunk_id: string
  document_title: string
  section?: string
  excerpt: string
  relevance: string
  metadata?: Record<string, string>
}

export type RecoverySuggestion = {
  title: string
  category: SuggestionCategory
  priority: RecoveryPriority
  actions: string[]
  rationale: string
  caution?: string
  sources: RecoverySourceCitation[]
}

export type IncidentRecoveryRequest = {
  use_gemini?: boolean
  top_k?: number
  optional_notes?: string
}

export type IncidentRecoveryResponse = {
  bfi: {
    classification?: string
    score?: number
    max_possible_score?: number
    full_max_score?: number
    favorability_percent_full?: number
    drivers_reporting?: number
    drivers_total?: number
    factors?: Array<Record<string, unknown>>
  }
  current_conditions: Array<{
    kind: 'driver' | 'input'
    label: string
    value?: unknown
    points?: number
    detail?: string | null
    note?: string | null
  }>
  evidence: {
    context_summary: string
    supporting_chunks: Array<{
      chunk_id: string
      text: string
      retrieval_summary: string
      metadata: { document_title?: string; section?: string; chapter?: string }
    }>
  }
  recovery: {
    situation_summary: string
    recovery_suggestions: RecoverySuggestion[]
    monitoring_recommendations: string[]
    confidence?: { level?: string; percent?: number; reason?: string }
    generation_mode?: string
    rag_grounded?: boolean
  }
  gemini_status?: string
}
