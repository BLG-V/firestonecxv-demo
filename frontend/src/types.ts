export interface EnterpriseSummary {
  id?: string
  enterprise_id?: string
  name?: string
  enterprise_name?: string
  industry?: string
  region?: string
  home_region?: string
  primary_segment_name?: string | null
  scenario?: string
}

export interface AIAnalysisResult {
  summary: string
  findings: string[]
  suggested_actions: string[]
  limitations: string[]
  model: string
  generated_at: string
  data_mode: string
  decision_status: string
}

export interface Evidence {
  field_path: string
  field_value: string | number | boolean | null
  source: string
  as_of: string
}

export interface ChainPosition {
  position_id?: number
  id?: number
  chain_id: string
  chain_name: string
  segment_id: string
  segment_name: string
  match_level: string
  match_score: number | null
  score_kind?: string
  status: string
  evidence: Evidence[]
}

export interface Veto {
  rule_name?: string
  detail?: string
  impact?: string
}

export interface DataGap {
  missing_field?: string
  impact?: string
}

export interface ExplanationDriver {
  factor_name?: string
  contribution?: number
  direction?: string
  human_readable_explanation?: string
  evidence?: Evidence[]
}

export interface ChainProfile {
  enterprise_id: string
  enterprise_name: string
  where: {
    positions: ChainPosition[]
    abstained: boolean
    abstain_reason?: string | null
    missing_signals?: string[]
  }
  worth: null | {
    icv_score: number | null
    segment_sv: number | null
    sv_dimensions?: Record<string, number | null>
    firm_cf: number | null
    risk_rd: number | null
    rank_in_segment?: number | null
    [key: string]: unknown
  }
  decision: null | {
    decision_type?: string
    grade?: string | null
    decision_status?: string
    attractiveness?: number | null
    landing_prob?: number | null
    carrier_match?: number | null
    vetoes?: Veto[]
    [key: string]: unknown
  }
  decision_status?: string
  data_stale?: boolean
  data_gaps?: Array<string | DataGap>
  explanation: null | {
    conclusion?: string
    score_summary?: {
      score?: number
      rank_in_segment?: number | null
      summary_text?: string
    }
    drivers?: ExplanationDriver[]
    vetoes?: Veto[]
    data_gaps?: DataGap[]
    suggested_actions?: string[]
  }
  data_as_of?: string
  data_mode?: string
}

export interface ChainHealth {
  chain_id: string
  chain_name: string
  region_code?: string
  period?: string
  data_as_of?: string
  segments: Array<{
    segment_id: string
    segment_name: string
    health_status?: string
    local_firm_count?: number | null
    has_leader?: boolean | null
    gap_level?: string
  }>
}

export interface SegmentEnterprise {
  enterprise_id?: string
  id?: string
  enterprise_name?: string
  name?: string
  match_level?: string
  match_score?: number | null
  score_kind?: string
  status?: string
}

export interface GapAnalysis {
  segment_id: string
  segment_name: string
  local_firm_count?: number | null
  expected_firm_count?: number | null
  gap_level?: string
  missing_tiers?: string[]
  cross_region_candidates?: Array<{
    enterprise_id: string
    enterprise_name: string
    home_region?: string
    icv_score?: number | null
    attractiveness?: number | null
    grade?: string | null
    top_reason?: string
  }>
  data_as_of?: string
}
