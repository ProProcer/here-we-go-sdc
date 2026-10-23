import { Fragment } from 'react';
import PriorityEvidence from '../components/PriorityEvidence';
import PlanDetails from '../components/PlanDetails';
import FutureScenarios from '../components/FutureScenarios';
import SDGImpact from '../components/SDGImpact';
import { Chip, date, Disclosure, EmptyState, ExternalLink, Icon } from '../components/ui';
import type { CourseStatus, Gap, LearningStep, Plan, PriorityEvidence as PriorityData, Profile, RoleData, ScenarioId, SdgConnection } from '../types';

function Sdg({ connection }: { connection: SdgConnection }) {
  return <div className="sdg-connection"><Chip>{connection.sdg_id} · Target {connection.target_id}</Chip><p className="mini-label">{connection.scope === "role_application" ? "Application in this role" : connection.scope === "career_preparation" ? "Career preparation" : "Skill development"}</p><p>{connection.rationale}</p><p className="caption">{connection.contribution} · {connection.evidence_kind} connection</p><ExternalLink url={connection.evidence_url}>Read the UN target</ExternalLink></div>;
}
function priorityExplanation(gap: Gap | undefined, synthetic: boolean, evidence?: PriorityData) {
  if (!gap) return 'Optional software learning objective, chosen by you.';
  const decision = evidence?.decisions.find(row => row.skill_id === gap.skill_id);
  const research = decision?.effective_evidence_adjustment ?? decision?.adjustment ?? 0;
  const scenario = decision?.scenario_adjustment ?? (synthetic ? gap.applied_adjustment : 0);
  return gap.applied_adjustment || research || scenario ? `Occupational priority ${gap.baseline_priority.toFixed(2)} → ${gap.adjusted_priority.toFixed(2)}. Hypothetical scenario adjustment: ${scenario.toFixed(3)}. Reviewed research adjustment: ${research.toFixed(3)}. These change learning emphasis, not your skills or personal fit. See the priority explanation below for evidence and policy limits.` : `Baseline learning priority ${gap.baseline_priority.toFixed(2)}, based on the selected role's requirement importance. It does not measure your proficiency.`;
}
export default function Roadmap({ data, plan, courseStatus, profile, sessionToken, pending, onBack, onDetails, onScenario, onExport }: {
  data: RoleData; plan: Plan; courseStatus: CourseStatus | null; profile: Profile; sessionToken: string | null; pending: boolean; onBack: () => void; onDetails: () => void;
  onScenario: (id: ScenarioId) => void; onExport: () => void;
}) {
  const { match: role, outlook } = data;
  const courses = new Map(plan.selected_courses.map(course => [course.course_id, course]));
  const gaps = new Map(plan.prioritized_gaps.map(gap => [gap.skill_id, gap]));
  const labels = new Map([...profile.skills, ...plan.prioritized_gaps, ...role.software_learning_options, ...(plan.sdg_summary?.skills || [])].map(skill => [skill.skill_id, skill.label]));
  const totalSteps = plan.milestones.reduce((total, milestone) => total + milestone.steps.length, 0);
  const scenario = outlook.scenario;
  const renderStep = (step: LearningStep) => {
    const course = step.course_id ? courses.get(step.course_id) : undefined, gap = gaps.get(step.skill_ids[0]);
    const connections = plan.sdg_connections.filter(connection => (!connection.scope || connection.scope === 'learning') && connection.skill_ids.some(id => step.skill_ids.includes(id)));
    const preview = step.learning_goal.replace(/ through a documented self-study objective while no verified course is available\.?$/i, '');
    return <details className="learning-step" key={step.order}><summary><span className="step-number">{step.order}</span><div className="step-preview"><span className="mini-label">{step.skill_ids.map(id => labels.get(id) || 'Learning skill').join(' · ')}</span><h3>{preview}</h3><p>{gap ? `Learning priority ${gap.adjusted_priority.toFixed(2)}` : 'An optional software direction'}</p></div><span className="step-toggle" aria-hidden="true"><Icon name="chevron" /></span></summary><div className="step-content"><h4>Full learning objective</h4><p>{step.learning_goal}</p><h4>Put it into practice</h4><p>{step.practice_activity}</p><h4>Show your progress</h4><p>{step.completion_evidence}</p><h4>Why this step?</h4><p>{priorityExplanation(gap, scenario.synthetic, outlook.learning_priority_evidence)}</p><h4>Learning resource</h4>{course ? <><p><ExternalLink url={course.course_url}>{course.title}</ExternalLink> · {course.provider}</p><p>{course.duration.display_text} · {course.cost.access.replaceAll('_', ' ')} {course.cost.currency || ''} {course.cost.amount} · Verified {date(course.last_verified_at)}</p><p>Prerequisites: {course.prerequisite_skill_ids.map(id => labels.get(id) || id).join(', ') || 'None listed'}</p></> : <div className="unavailable-resource">No matching course has been verified in our catalog yet. Use the practice activity above, or browse the provider catalog to find a resource. <ExternalLink url="https://www.open.edu/openlearn/free-courses/full-catalogue">Browse OpenLearn courses</ExternalLink></div>}{connections.length > 0 && <Disclosure title="SDG connections">{connections.map((connection, i) => <Sdg key={i} connection={connection} />)}</Disclosure>}</div></details>;
  };
  const milestones = (later: boolean) => plan.milestones.map((milestone, index) => {
    const steps = milestone.steps.filter(step => later ? step.order > 5 : step.order <= 5);
    return steps.length > 0 && <Fragment key={index}><h3 className="milestone-heading">{milestone.title}</h3>{steps.map(renderStep)}</Fragment>;
  });
  return <section id="detail" className="screen">
    <button id="back-to-matches" className="text-button back-link" disabled={pending} onClick={onBack}>← Back to career matches</button>
    <div className="page-heading"><div><span className="eyebrow">ONE STEP CLOSER TO WHAT'S NEXT</span><h1>Your path forward.</h1><p className="page-intro">Build on your strengths. Prepare for a first role, a career move or development at work.</p></div><button id="export-plan" className="button secondary" disabled={pending} onClick={onExport}>Export JSON <span aria-hidden="true">↓</span></button></div>
    <div className="roadmap-layout"><div className="roadmap-main"><div className="selected-career"><span className="role-mark"><Icon name="career" /></span><div><span id="detail-family" className="mini-label">{role.family}</span><h2 id="detail-title">{role.role_title}</h2><div className="chips role-sdg-tags">{data.detail.sdg_connections?.map((connection, index) => <Chip key={index}>{connection.sdg_id} · Target {connection.target_id}</Chip>)}</div><button id="open-role-details" className="text-button" disabled={pending} onClick={onDetails}>About this match ↗</button></div><div className="personal-fit"><strong id="detail-fit">{role.fit_score.toFixed(2)}</strong><span>Personal fit / 100</span></div></div>
      <div className="section-heading"><h2>Your learning journey</h2><span id="plan-summary" className="caption">{plan.prioritized_gaps.length} learning objectives</span></div>
      <div id="course-availability">{plan.uncovered_skill_ids.length > 0 && <div className="resource-note"><Icon name="book" /><div><strong>Verified courses unavailable for {plan.uncovered_skill_ids.length} {plan.uncovered_skill_ids.length === 1 ? 'objective' : 'objectives'}</strong><p>Your learning objectives and practice activities are ready to explore.</p></div></div>}</div>
      <div id="milestones" className="timeline">{totalSteps ? <>{milestones(false)}{totalSteps > 5 && <Disclosure id="remaining-steps" title={`Show ${totalSteps - 5} more learning steps`} className="more-steps">{milestones(true)}</Disclosure>}</> : <EmptyState title="You're ready for another step" symbol="path">No remaining learning objectives for these selections. Explore optional software in the role details.</EmptyState>}</div>
    </div><FutureScenarios roleId={role.role_id} token={sessionToken} selected={scenario.scenario_id} pending={pending} onScenario={onScenario} /></div>
    {plan.sdg_summary && <SDGImpact summary={plan.sdg_summary} />}
    <div className="roadmap-help">
      <PriorityEvidence evidence={outlook.learning_priority_evidence} labels={labels} />
      {!plan.sdg_summary && <Disclosure help title="SDG connections"><p className="caption">These are curated, conditional connections to UN targets. SDG 4.4 describes employment-related learning. Role connections use occupational requirements, including skills you already have; they do not disappear when a skill is confirmed.</p><div id="sdg-connections">{plan.sdg_connections.length ? plan.sdg_connections.map((connection, i) => <Sdg key={i} connection={connection} />) : <p>No supported SDG relationships for these objectives.</p>}</div></Disclosure>}
      {scenario.synthetic && <Disclosure help id="scenario-assumptions" title="Scenario assumptions"><div id="scenario-assumption-text">{[scenario.interpretation, ...scenario.assumptions].join(' ')}</div></Disclosure>}
      <PlanDetails plan={plan} courseStatus={courseStatus} profile={profile} />
    </div>
  </section>;
}
