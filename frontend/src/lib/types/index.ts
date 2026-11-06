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
}

export interface EvidenceItem {
  id: string;
  label: string | null;
  url: string | null;
  content: string | null;
  evidence_type: string | null;
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
