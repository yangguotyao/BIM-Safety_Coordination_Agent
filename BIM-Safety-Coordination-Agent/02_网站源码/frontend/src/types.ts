export type CaseStatus =
  | 'draft'
  | 'analyzing'
  | 'needs_evidence'
  | 'pending_review'
  | 'approved'
  | 'rectifying'
  | 'pending_verification'
  | 'closed'
  | 'reopened'
  | 'rejected'

export interface CheckItem {
  name: string
  result: string
  source?: string
  note?: string
}

export interface Finding {
  kind?: string
  task_ids?: string[]
  pair_id?: string
  finding_id: string
  hazard: string
  result: 'risk_candidate' | 'no_issue_in_checked_items' | 'needs_evidence' | string
  risk_level?: string
  bim_guids: string[]
  evidence_ids: string[]
  rule_ids: string[]
  checks: CheckItem[]
  uncertainties: string[]
  provenance?: string
  scope_note?: string
  inputs?: Record<string, unknown>
  narrative?: {
    summary: string
    reasoning_basis?: { type: string; id: string }[]
    uncertainties?: string[]
    label?: string
  }
}

export interface Control {
  control_id: string
  finding_id: string
  action: string
  owner: string
  verification_requirements: string[]
  verification_criteria?: VerificationCriteria
  status: string
  version: number
  provenance?: string
  scope_note?: string
}

export interface VerificationCriteria {
  coordination_required?: boolean
  guardrail_required: boolean
  min_height_m: number
  fixed_required: boolean
  continuous_required: boolean
  manual_requirements: string[]
}

export interface TaskSpec {
  request: string
  zone_id: string
  as_of: string
  focus: string[]
  selected_tools: string[]
  retrieval_query: string
  needs_clarification: boolean
  clarification: string
  context_inherited: boolean
  mode: string
}

export interface DecisionPackage {
  execution_plan?: ExecutionPlan
  evidence_trace?: EvidenceTrace
  assurance?: DecisionAudit
  evidence_gaps?: EvidenceGap[]
  memory?: {case_messages:number;project_examples:{case_id:string;title:string;source_kind:string}[]}
  case_id: string
  run_id: string
  status: string
  evidence: string[]
  governing_rules: Rule[]
  owners: string[]
  assumptions: string[]
  scope: string
  mode: string
}

export interface Review {
  verification_snapshot?: Record<string, VerificationCriteria>
  decision: 'approve' | 'reject' | 'modify' | string
  reviewer: string
  reviewed_at: string
  control_version: number
  comment: string
}

export interface Implementation {
  owner: string
  implemented_at: string
  comment: string
  provenance?: string
}

export interface Verification {
  verified_at: string
  evidence_ids: string[]
  checks: CheckItem[]
  reviewer_confirmed: boolean
  result: string
  remaining_risk: string
  reviewer?: string
}

export interface CaseRecord {
  scope?: ScopeAnnotation | null
  request_text?: string
  task_spec?: TaskSpec | null
  safety_state?: Record<string, any> | null
  decision_package?: DecisionPackage | null
  schema_version: string
  case_id: string
  title: string
  project_id: string
  model_id: string
  model_version: string
  task_id: string
  zone_id: string
  as_of: string
  status: CaseStatus
  version: number
  bim_guids: string[]
  evidence_ids: string[]
  rule_ids: string[]
  findings: Finding[]
  controls: Control[]
  review: Review | null
  implementation: Implementation | null
  verification: Verification | null
  assumptions: string[]
  provenance: string
  mode: string
  last_run_id: string | null
  analysis_incomplete: number
  created_at: string
  updated_at: string
  control_version: number
  allowed_actions: string[]
  versions: { case: number; rules: string }
}

export interface Evidence {
  evidence_id: string
  project_id: string
  model_id: string
  model_version: string
  zone_id: string
  bim_guids: string[]
  file_path: string | null
  kind: string
  captured_at: string
  stage: 'before' | 'after' | string
  provenance: string
  observation: Record<string, any>
  label: string
  source?: string
  image_url?: string
  perception?: Record<string, any>
}

export interface Rule {
  rule_id: string
  standard: string
  clause: string
  text: string
  text_kind: string
  source_path: string
  pdf_page: number
  source_url: string
  status: 'active' | 'retired' | string
  effective_from?: string
  checked_on?: string
  jurisdiction?: string
  applicability?: string
  version?: string
  human_page_checked?: number
  score?: number
}

export interface AgentEvent {
  id?: number
  seq: number
  node: string
  role: string
  tool: string | null
  input_summary: string
  output: Record<string, any>
  status: string
  error?: string | null
  rationale: string
  at: string
}

export interface Run {
  execution_plan?:ExecutionPlan
  evidence_trace?:EvidenceTrace
  assurance?:DecisionAudit
  evidence_gaps?:EvidenceGap[]
  runtime?:{state:string;attempts:number;recoveries:number;error_code:string|null;can_resume:boolean;cancel_requested:number}
  run_id: string
  case_id?: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
  mode?: string
  events?: AgentEvent[]
  trace?: any[]
  model_calls?: ModelCall[]
}

export interface CaseEvent {
  id: number
  case_id: string
  at: string
  status: string
  event: string
  actor: string
  detail: Record<string, any>
  provenance: string
}

export interface CaseBundle {
  activity_plan?: ActivityPlan | null
  coordination?: Record<string,any>
  site_notes?: SiteNote[]
  site_text?: Record<string,any>
  spatial?: Record<string,any>
  case: CaseRecord
  evidence: Evidence[]
  rules: Rule[]
  events: CaseEvent[]
  runs: Run[]
  context?: { zone: Record<string, any>; task: Record<string, any> }
  model_calls?: ModelCall[]
}

export interface ModelCall {
  id: number
  purpose: string
  model: string
  status: string
  elapsed_ms: number
  usage: Record<string, number>
  error?: string
}

export interface ExecutionPlan {
  version:string
  focus:string[]
  strategy:string
  subtasks:{goal_id:string;title:string;tools:string[]}[]
  steps:{tool:string;depends_on:string[];permission:string;mandatory:boolean;arguments:Record<string,unknown>}[]
  budget:{max_replans:number;max_model_calls:number;deadline_seconds:number}
  replanning?:{reason:string;round:number;next_action:string}
}
export interface EvidenceGap {gap_id:string;field:string;message:string;action:string;evidence_id?:string;blocking:boolean}
export interface DecisionAudit {status:string;method:string;checks:string[];issues:{code:string;message:string}[];input_hash:string;scope:string}
export interface EvidenceTrace {
  input_hash:string
  facts:{id:string;property:string;value:unknown;unit:string|null;source_id:string;source_kind:string;bim_guids:string[];status:string}[]
  nodes:{id:string;kind:string;label:string;result?:string;source?:Record<string,unknown>}[]
  edges:{from:string;to:string;relation:string}[]
}

export interface ScopeAnnotation {
  guid:string
  edge_index:number
  worker_point_m:number[] | null
  worker_point_source:'simulated' | 'human_observed'
  boundary_confirmed:boolean
  edge_segment_m?:number[][]
}
export interface Activity {
  task_id:string
  activity:string
  trade:string
  owner:string
  planned_start:string | null
  planned_end:string | null
  bim_guids:string[]
  workspace:{min:number[];max:number[]} | null
}
export interface ActivityPlan {
  revision:number
  activities:Activity[]
  history:{revision:number;reason:string;at:string;activities:Activity[]}[]
}
export interface SiteNote {
  note_id:string
  document_id:string
  version:number
  title:string
  source:string
  captured_at:string
  body:string
  current:boolean
  paragraphs:{id:string;text:string}[]
  analysis:Record<string,any> | null
}

export interface Health {
  ok: boolean
  mode: string
  demo_mode: boolean
  live_config_complete: boolean
  db: { ok: boolean; error: string | null }
  ifcopenshell: { available: boolean; version: string | null }
  model_cache: Record<string, any>
  demo_clock: string
  version: string
  data_root: string
  package_root: string
  ports: Record<string, number>
}

export interface Summary {
  model: Record<string, any>
  storey: Record<string, any>
  element_count: number
  storey_element_count: number
  preview_mesh_count: number
  cases_total: number
  status_counts: Record<string, number>
  active_rules: number
  retired_rules: number
  evidence_count: number
  open_cases: number
  risk_candidates: number
  acceptance: { total: number; passed: number }
  latest_runs: Run[]
  recent_cases: CaseRecord[]
  demo_clock: string
  mode: string
}

export interface ElementRow {
  model_id: string
  guid: string
  ifc_class: string
  name: string
  storey_guid: string
  storey_name: string
  geometry_available?: boolean
  bbox_m?: { min: number[]; max: number[] }
}

export interface MeshData {
  guid: string
  ifc_class: string
  name?: string
  vertices: number[][]
  triangles: number[][]
  bbox_m?: { min: number[]; max: number[] }
  source?: string
  units?: string
}

export interface MeshPayload {
  model_id: string
  model_version: string
  coordinate_system: string
  target: Record<string, any>
  zone: Record<string, any>
  meshes: MeshData[]
  scope: Record<string, any>
  units: string
}

export interface AcceptanceResult {
  test_id: string
  name: string
  expected: string
  actual: string
  passed: boolean
  details: Record<string, any>
  case_id: string | null
  run_at?: string
}

export interface AcceptanceSummary {
  total: number
  executed: number
  passed: number
  failed: number
  results: AcceptanceResult[]
}
