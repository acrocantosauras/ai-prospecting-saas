export interface Workspace {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface ClientProfile {
  id: string;
  workspace_id: string;
  name: string;
  website: string | null;
  description: string | null;
  products_services: string | null;
  value_proposition: string | null;
  target_audience: string | null;
  problems_solved: string | null;
  usp: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClientProfileCreate {
  workspace_id: string;
  name: string;
  website?: string | null;
  description?: string | null;
  products_services?: string | null;
  value_proposition?: string | null;
  target_audience?: string | null;
  problems_solved?: string | null;
  usp?: string | null;
  is_active?: boolean;
}

export interface ClientProfileUpdate {
  name?: string | null;
  website?: string | null;
  description?: string | null;
  products_services?: string | null;
  value_proposition?: string | null;
  target_audience?: string | null;
  problems_solved?: string | null;
  usp?: string | null;
  is_active?: boolean | null;
}

export interface ICPProfile {
  id: string;
  workspace_id: string;
  client_profile_id: string | null;
  name: string;
  target_industries: string | null;
  sub_industries: string | null;
  target_countries: string | null;
  target_regions: string | null;
  company_size: string | null;
  employee_count_min: number | null;
  employee_count_max: number | null;
  revenue_min: string | null;
  revenue_max: string | null;
  preferred_company_types: string | null;
  target_audience: string | null;
  decision_maker_roles: string | null;
  additional_criteria: string | null;
  max_prospects: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ICPProfileCreate {
  workspace_id: string;
  client_profile_id?: string | null;
  name: string;
  target_industries?: string | null;
  sub_industries?: string | null;
  target_countries?: string | null;
  target_regions?: string | null;
  company_size?: string | null;
  employee_count_min?: number | null;
  employee_count_max?: number | null;
  revenue_min?: string | null;
  revenue_max?: string | null;
  preferred_company_types?: string | null;
  target_audience?: string | null;
  decision_maker_roles?: string | null;
  additional_criteria?: string | null;
  max_prospects?: number;
  is_active?: boolean;
}

export interface ICPProfileUpdate {
  name?: string | null;
  target_industries?: string | null;
  sub_industries?: string | null;
  target_countries?: string | null;
  target_regions?: string | null;
  company_size?: string | null;
  employee_count_min?: number | null;
  employee_count_max?: number | null;
  revenue_min?: string | null;
  revenue_max?: string | null;
  preferred_company_types?: string | null;
  target_audience?: string | null;
  decision_maker_roles?: string | null;
  additional_criteria?: string | null;
  max_prospects?: number | null;
  is_active?: boolean | null;
}

export type BatchStatus = 'pending' | 'running' | 'completed' | 'failed';
export type BatchStage =
  | 'configured'
  | 'discovering_companies'
  | 'researching_companies'
  | 'discovering_decision_makers'
  | 'enriching_contacts'
  | 'identifying_problems'
  | 'matching_solutions'
  | 'qualifying'
  | 'completed';

export interface ProspectBatch {
  id: string;
  workspace_id: string;
  icp_profile_id: string;
  client_profile_id: string | null;
  name: string;
  status: BatchStatus;
  current_stage: BatchStage | null;
  total_discovered: number;
  total_researched: number;
  total_enriched: number;
  total_qualified: number;
  error_message: string | null;
  source_mode: string;
  requested_prospect_count: number;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProspectBatchCreate {
  workspace_id: string;
  icp_profile_id: string;
  client_profile_id?: string | null;
  name: string;
  requested_prospect_count: number;
}

export interface ProspectBatchList {
  items: ProspectBatch[];
  total: number;
}

export interface Prospect {
  id: string;
  batch_id: string;
  company_id: string | null;
  decision_maker_id: string | null;
  first_name: string | null;
  last_name: string | null;
  full_name: string | null;
  email: string | null;
  role: string | null;
  linkedin_url: string | null;
  instagram_url: string | null;
  company_name: string | null;
  company_website: string | null;
  industry: string | null;
  country: string | null;
  research_summary: string | null;
  business_problem: string | null;
  problem_evidence: string | null;
  solution_match: string | null;
  qualification_score: number;
  qualification_reasons: string | null;
  research_confidence: string | null;
  missing_information: string | null;
  source_links: string | null;
  is_ready_for_outreach: boolean | null;
  research_status: string | null;
  research_last_successful_at: string | null;
  decision_maker_status: string | null;
  refresh_needed: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompanyInfo {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  location: string | null;
  country: string | null;
  city: string | null;
  description: string | null;
  products_services: string | null;
  company_size: string | null;
  employee_count: string | null;
  revenue: string | null;
  linkedin_url: string | null;
  instagram_url: string | null;
  source_url: string | null;
  source_name: string | null;
  research_status: string | null;
  research_last_attempted_at: string | null;
  research_last_successful_at: string | null;
  research_error: string | null;
}

export interface DecisionMakerInfo {
  id: string;
  first_name: string | null;
  last_name: string | null;
  full_name: string | null;
  job_title: string | null;
  professional_profile_url: string | null;
  profile_source: string | null;
  is_primary: boolean;
  status: string | null;
  last_observed_at: string | null;
  observation_confidence: number | null;
  evidence_excerpt: string | null;
}

export interface EvidenceItem {
  id: string;
  label: string | null;
  url: string | null;
  content: string | null;
  evidence_type: string | null;
  retrieved_at: string | null;
  publication_date: string | null;
  is_accessible: boolean | null;
  verification_status: string | null;
}

export interface EnrichmentRecord {
  id: string;
  provider: string | null;
  provider_record_id: string | null;
  email: string | null;
  email_status: string | null;
  email_confidence: number | null;
  linkedin_url: string | null;
  instagram_url: string | null;
  other_profiles: string | null;
}

export interface VerificationRecord {
  id: string;
  email: string | null;
  status: string | null;
  provider: string | null;
  details: string | null;
}

export interface ProspectDetail extends Prospect {
  company: CompanyInfo | null;
  decision_maker: DecisionMakerInfo | null;
  evidence: EvidenceItem[];
  enrichment_records: EnrichmentRecord[];
  verification_records: VerificationRecord[];
}

export interface ProspectList {
  items: Prospect[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadExportRow {
  lead_id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  company: string | null;
  website: string | null;
  role: string | null;
  client_id: string;
  status: string;
  draft_date: string | null;
  notes: string | null;
}

export * from './auth';

export interface HealthResponse {
  status: string;
}

export interface RootResponse {
  name: string;
  version: string;
  mode: boolean;
  docs: string;
}

export const STAGE_LABELS: Record<BatchStage, string> = {
  configured: 'Configuration',
  discovering_companies: 'Company Discovery',
  researching_companies: 'Company Research',
  discovering_decision_makers: 'Decision-Maker Identification',
  enriching_contacts: 'Contact Enrichment',
  identifying_problems: 'Problem Identification',
  matching_solutions: 'Solution Matching',
  qualifying: 'Qualification',
  completed: 'Complete',
};

// Engine types

export interface StageRun {
  stage: string;
  status: string;
  detail: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface EngineBatchSnapshot {
  id: string;
  workspace_id: string;
  name: string;
  status: string;
  current_stage: string | null;
  source_mode: string;
  requested_prospect_count: number;
  total_discovered: number;
  total_discovered_companies: number | null;
  total_researched: number;
  total_enriched: number;
  total_qualified: number;
  total_rejected: number | null;
  error_message: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UsageTotals {
  total_cost_usd: number;
  total_calls: number;
  by_capability: Record<string, number>;
  per_company_usd: number | null;
  per_decision_maker_usd: number | null;
  per_verified_email_usd: number | null;
  per_qualified_prospect_usd: number | null;
  budget_usd: number | null;
}

export interface QualificationDecision {
  id: string;
  company_id: string | null;
  prospect_id: string | null;
  scope: string;
  status: string;
  score: number;
  confidence: number;
  reasons: string | null;
  missing: string[];
  evidence_urls: string[];
  gates: Record<string, unknown>[];
  policy: Record<string, unknown>;
  created_at: string;
}

export interface ProspectVerification {
  prospect_id: string;
  email: string | null;
  email_verified: boolean;
  email_status: string | null;
  qualification_status: string | null;
  missing_information: string[];
  enrichment: Record<string, unknown>[];
  verification: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
}

export interface CompanyResearch {
  provider: string;
  what_it_does: string | null;
  last_attempted_at: string | null;
  last_successful_at: string | null;
  research_status: string | null;
  error_message: string | null;
  what_it_sells: string | null;
  who_it_serves: string | null;
  positioning: string | null;
  public_developments: string | null;
  observable_signals: unknown[];
  missing_information: unknown[];
  confidence: number | null;
  synthetic: boolean;
  research_timestamp: string;
}

export interface DemoReadiness {
  total_prospects: number;
  fresh_prospects: number;
  aging_prospects: number;
  stale_prospects: number;
  incomplete_prospects: number;
  decision_makers_with_fresh_evidence: number;
  broken_source_urls: number;
  qualification_blockers: string[];
  last_successful_refresh: string | null;
  demo_ready: boolean;
}

export interface CompanyEvidence {
  company_id: string;
  company_name: string;
  research: CompanyResearch | null;
  evidence: Record<string, unknown>[];
  freshness: Record<string, unknown> | null;
}

export interface ProviderStatus {
  name: string;
  capability: string;
  state: string;
  synthetic: boolean;
  available: boolean;
  detail: string | null;
  cost_per_call_usd: number;
}

export interface ProviderOverview {
  mode: string;
  providers: ProviderStatus[];
  policy: Record<string, unknown>;
  notes: string[];
}

export const STAGE_DESCRIPTIONS: Record<BatchStage, string> = {
  configured: 'Batch configured and ready to start.',
  discovering_companies: 'Finding companies matching your ICP criteria.',
  researching_companies: 'Researching each company\'s profile and offerings.',
  discovering_decision_makers: 'Identifying key decision-makers at each company.',
  enriching_contacts: 'Enriching contact details and social profiles.',
  identifying_problems: 'Identifying relevant business problems for each prospect.',
  matching_solutions: 'Matching your offering to each prospect\'s needs.',
  qualifying: 'Scoring and ranking prospects by fit.',
  completed: 'Prospecting complete. Review your results.',
};
