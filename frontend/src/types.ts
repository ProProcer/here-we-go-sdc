// Fields consumed by the UI. API responses retain their full metadata for export.
export type Screen = 'intake' | 'review' | 'explore' | 'detail';
export type ScenarioId = 'baseline' | 'moderate_ai_change' | 'rapid_ai_change';
export interface Skill { skill_id: string; label: string }
export interface ProfileSkill extends Skill {
  confirmation: 'confirmed' | 'unverified';
  level: 'unknown' | 'beginner' | 'intermediate' | 'advanced';
  evidence: string[];
  level_assessment?: { method: 'ai_estimate'; model: string; provider?: 'groq' | 'runpod' | 'gemini' | null; confidence: string; rationale: string; evidence_indices: number[] } | null;
}
export interface Profile {
  assessment_status?: { status: 'completed' | 'failed' | 'not_configured'; provider: string; message: string; assessed_skill_count: number; error_code: string | null; primary_provider?: string; used_backup?: boolean } | null;
  skills: ProfileSkill[];
  constraints: { budget_myr: number | null; hours_per_week: number | null };
  interests: string[];
  desired_role_id: string | null;
  warnings: string[];
}
export interface ProfileResponse { session_id: string; revision: number; profile: Profile }
export interface RoleSummary { role_id: string; role_title: string; family: string }
export interface Contribution extends Skill { evidence: string[]; reason: string; importance: number }
export interface SoftwareOption extends Skill { group_familiarity_evidenced: boolean }
export interface Match extends RoleSummary {
  rank: number;
  fit_score: number;
  manually_selected: boolean;
  matched_skills: Contribution[];
  missing_skills: Contribution[];
  software_learning_options: SoftwareOption[];
  warnings: string[];
  score_breakdown: {
    general_fulfilment: number;
    proficiency_comparisons: { skill_id: string; label: string; importance: number; required_source_level: number | null; profile_level: string; profile_level_proxy: number | null; fulfilment: number; status: string }[];
    profile_alignment: number;
    profile_alignment_weight: number;
    general_coverage_weight: number;
    evidence_breadth: number;
    supported_skill_count: number;
    alignment_contributions: { skill_id: string; label: string; distinctiveness: number; role_affinity: number; normalized_weight: number; contribution: number }[];
    readiness_weight: number;
    preference_weight: number;
    coverage: {
      matched_software_skill_ids: string[];
      general_coverage: number | null;
      software_group_coverage: number | null;
      software_exact_coverage: number | null;
    };
  };
}
export interface EvidenceSource {
  source_id: string; source_url: string; title: string; publisher: string;
  published_at: string; retrieved_at: string; coverage: string; limitations: string;
}
export interface Outlook {
  general_research?: { title: string; publisher: string; source_url: string; published_at: string; checked_at: string; summary: string }[];
  learning_priority_evidence?: PriorityEvidence;
  baseline_label: string;
  available_scenarios: ScenarioId[];
  scenario: { scenario_id: ScenarioId; synthetic: boolean; interpretation: string; assumptions: string[] };
  sources: EvidenceSource[];
  signals: { source_id: string; signal_id: string; claim: string }[];
  tasks: { task_id: string; label: string; interpretation: string; evidence_status: string; mapping_basis: string | null; signal_ids: string[] }[];
  limitations: string[];
}
export interface Evidence {
  chains: {
    task_label: string;
    finding: { claim: string };
    source: EvidenceSource;
    skill_labels: Record<string, string>;
    reasoning: {
      study_period_start: string; study_period_end: string; interpretation_status: string;
      task_change: string; assumptions: string[]; human_responsibilities: string[]; limitations: string[];
      skill_implications: { skill_id: string; direction: string; rationale: string; less_emphasis: string[]; more_emphasis: string[] }[];
    };
  }[];
}
export interface Refresh { refresh: { status: string; message: string; attempted_at: string } | null }
export interface CourseStatus { status: 'available' | 'empty'; verified_course_count: number; updated_at: string | null; mode: 'verified_cache' }
export interface RoleData {
  match: Match; detail: { role: { description: string } }; outlook: Outlook; evidence: Evidence; refresh: Refresh;
  skillEvidence: SkillEvidence | null; roleImpacts: RoleImpacts | null;
}
export interface ReviewedInterpretation {
  news_id: string; rationale: string; applicability_conditions: string[]; human_checks: string[];
  source: { source_url: string; publisher: string; published_at?: string };
  supporting_findings: { claim: string; quote: string; evidence_type: string; reference: { document_id: string; passage_id: string } }[];
}
export interface SkillEvidence {
  changes_weights: false;
  approved_conditional_skill_evidence: (ReviewedInterpretation & { skill_id: string; skill_label: string })[];
  pending_mapping_reviews: number; unassessed_pairs: number; articles_awaiting_shared_review: number;
}
export interface RoleImpacts {
  changes_weights: false;
  approved_conditional_role_impacts: (ReviewedInterpretation & { assessment_sha256: string; tasks: { task_id: string; label: string }[] })[];
  candidate_pairs: number; unassessed_candidate_pairs: number; skill_pairs_pending: number; coverage: string;
}
export interface PriorityEvidence {
  policy_version: string; maximum_adjustment: number; basis: string;
  decisions: {
    skill_id: string; status: string; adjustment: number; independent_studies: number; publishers: number;
    contributing_assessment_ids: string[]; excluded_assessment_ids: string[];
    scenario_adjustment?: number; effective_evidence_adjustment?: number;
  }[];
  rejected_assessments: { assessment_id: string; reason: string }[];
}
export interface Gap extends Skill { baseline_priority: number; adjusted_priority: number; applied_adjustment: number }
export interface Course {
  course_id: string; title: string; course_url: string; provider: string; last_verified_at: string;
  duration: { display_text: string }; cost: { access: string; currency: string | null; amount: number };
  prerequisite_skill_ids: string[];
}
export interface SdgConnection {
  scope?: 'learning' | 'role_application';
  sdg_id: string; target_id: string; rationale: string; contribution: string;
  evidence_kind: string; evidence_url: string; skill_ids: string[];
}
export interface LearningStep {
  order: number; skill_ids: string[]; course_id: string | null;
  learning_goal: string; practice_activity: string; completion_evidence: string;
}
export interface Plan {
  prioritized_gaps: Gap[]; selected_courses: Course[]; uncovered_skill_ids: string[];
  milestones: { title: string; steps: LearningStep[] }[]; sdg_connections: SdgConnection[];
  warnings: string[]; cost_totals: { currency: string; amount: number }[]; total_estimated_hours: number | null;
}
