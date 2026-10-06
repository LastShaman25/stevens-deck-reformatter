export type SlideKind = "title" | "thankyou" | "section" | "picture" | "content";

export interface SlidePlan {
  index: number;
  title: string;
  kind: SlideKind;
  layout: string;
  rationale: string;
  issues: string[];
  n_body: number;
  n_images: number;
  needs_review: boolean;
}

export interface Capabilities {
  openai?: boolean;
  ai?: AIConfiguration;
  libreoffice: boolean;
  gemini: boolean;
  claude?: boolean;
}

export interface AIConfiguration {
  configured: boolean;
  redesign_configured?: boolean;
  generation_configured?: boolean;
  independent_providers: boolean;
  generation_independent_providers?: boolean;
  redesigner?: {provider: string; model: string; configured: boolean};
  generator?: {provider: string; model: string; configured: boolean};
  planner: {provider: string; model: string; configured: boolean};
  reviewer: {provider: string; model: string; configured: boolean};
}

export interface SessionInfo {
  template_id?: 'cpe' | 'stevens';
  preview_generation?: Generation | null;
  generation?: Generation | null;
  revision_version?: number;
  session_id: string;
  name: string;
  slide_count: number;
  slides: SlidePlan[];
  capabilities: Capabilities;
  generated?: boolean;
  revisions?: Record<string, Revision>;
  ai_check?: number[];
  ai_results?: Record<string, AiFlag[]>;
  benchmarked?: boolean;
}

export interface AiFlag {
  type: string;
  severity: "low" | "med" | "high" | string;
  note: string;
  where: string;
}

export interface Revision {
  reset_emphasis?: boolean;
  tags: string[];
  instruction: string;
}

export interface ReviseResult {
  index: number;
  kind: string;
  applied: string[];
  reconstructed: boolean;
  preserved_diagram: boolean;
  changed: boolean;
  summary: string;
  hard_issues: number;
}

export interface ReviseResponse {
  ok: boolean;
  rerendered: boolean;
  result: ReviseResult | null;
}

export interface QualityCheck {
  label: string;
  status: "ok" | "warn" | "fail" | "off";
}

export interface Quality {
  score: number;
  checks: QualityCheck[];
  unresolved: number;
  gemini_flags: number;
  coverage_ok: boolean;
  diagrams_reconstructed: number;
  lint_fail?: number;
  lint_warn?: number;
  lint_clean?: boolean;
}

export interface BenchmarkResult {
  ok: boolean;
  benchmarked: boolean;
  deck?: string;
  slide_count?: number;
  total_benchmarks?: number;
}

export type Step = "upload" | "review" | "generate" | "download";

export interface Finding {
  priority?: 'high' | 'low';
  check?: string;
  can_approve?: boolean;
  affected_slides?: number[];
  id: string;
  code: string;
  message: string;
  severity: 'blocking' | 'review' | 'warning' | 'optional_pending';
  output_slide?: number;
  source_slide?: number;
  ai_source_slide?: number;
  slide?: number;
}

export interface Generation {
  preserved_image_regions?: number;
  added_slides?: {output_slide:number;kind:string;text:string;authorization:string}[];
  source_decisions?: Record<string,{action:'redesign'|'keep_original';reason:string;removed_artwork:number;extracted_logos?:number}>;
  qa_execution?: {requests:number;reviewed_slides:number;total_slides:number;complete:boolean;error:string;redesign_reviewed_slides?:number;redesign_review_status?:string};
  output_qa_repairs?: {attempt: number; targets: number[]; accepted: boolean; reason?: string}[];
  repair_stop_reason?: string | null;
  mode?: 'preserve' | 'ai';
  progress?: {stage: string; output_slide?: number; attempt?: number; completed_calls?: number; max_calls?: number | null; reviewed_slides?:number; total_slides?:number};
  pdf_available?: boolean;
  download_allowed?: boolean;
  usage?: {upload_requests: number; upload_tokens: number; token_limit?:number | null};
  ai_pipeline?: {status: string; failure_message?: string | null; changed_objects: number; completed_calls?: number; configuration: AIConfiguration;
    calls: {role: string; provider?: string; model?: string; status: string; message?: string}[];
    attempts: {attempt: number; accepted: boolean; changed_objects?: number; reason?: string}[]} | null;
  generation_id: string;
  candidate_sha256: string | null;
  state: 'checking' | 'ready' | 'needs_review' | 'failed' | 'error';
  built_slides: number;
  checks: Record<string, {status: string}>;
  findings: Finding[];
  human_decisions: {output_slide?:number|null;finding_ids: string[]; rationale: string}[];
  source_to_output_slides: Record<string, number[]>;
  corrections: {index: number; actions: {action: string; status: string; message: string}[]}[];
}
