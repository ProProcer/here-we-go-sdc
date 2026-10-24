import { t } from '../i18n';
import PriorityEvidence from '../components/PriorityEvidence';
import PlanDetails from '../components/PlanDetails';
import FutureScenarios from '../components/FutureScenarios';
import DependencyRoadmap from '../components/DependencyRoadmap';
import { Chip, Icon } from '../components/ui';
import type { CourseStatus, DependencyMap, Plan, Profile, RoadmapHorizon, RoleData, ScenarioId } from '../types';

export default function Roadmap({ data, plan, courseStatus, profile, sessionToken, pending, onBack, onDetails, onScenario, onExport, onSdg, weeklyHours, onPace, revision, horizon, onHorizon, onCurated, curated }: {
  data: RoleData; plan: Plan; courseStatus: CourseStatus | null; profile: Profile; sessionToken: string | null; pending: boolean;
  onBack: () => void; onDetails: () => void; onScenario: (id: ScenarioId) => void; onExport: () => void; onSdg: () => void;
  weeklyHours: number; onPace: (hours: number) => void; revision: number; horizon: RoadmapHorizon;
  onHorizon: (horizon: RoadmapHorizon) => void; onCurated: (map: DependencyMap | null) => void; curated: DependencyMap | null;
}) {
  const { match: role, outlook } = data;
  const labels = new Map([...profile.skills, ...plan.prioritized_gaps, ...role.software_learning_options].map(skill => [skill.skill_id, skill.label]));
  return <section id="detail" className="screen career-detail-page">
    <button id="back-to-matches" className="button secondary back-link" disabled={pending} onClick={onBack}>{t("← Back to career matches")}</button>
    <div className="page-heading"><div><span className="eyebrow">{t("ONE STEP CLOSER TO WHAT’S NEXT")}</span><h1>{t("Your path forward.")}</h1><p className="page-intro">{t("Build practical capabilities. Focus on the gaps that matter most.")}</p></div><button id="export-plan" className="button secondary" disabled={pending || !curated} onClick={onExport}>{t("Export JSON ")}<span aria-hidden="true">↓</span></button></div>
    <div className="roadmap-content"><div className="roadmap-main">
      <div className="selected-career"><span className="role-mark"><Icon name="career" /></span><div><span id="detail-family" className="mini-label">{t(role.family)}</span><h2 id="detail-title">{t(role.role_title)}</h2><button id="open-role-details" className="button secondary" disabled={pending} onClick={onDetails}>{t("About this match ")}<Icon name="arrow" /></button></div><div className="personal-fit"><strong id="detail-fit">{role.fit_score.toFixed(2)}</strong><span>{t("Personal fit / 100")}</span></div></div>
      <DependencyRoadmap data={data} plan={plan} token={sessionToken} revision={revision} weeklyHours={weeklyHours} onPace={onPace} horizon={horizon} onHorizon={onHorizon} onCurated={onCurated} />
    </div><FutureScenarios roleId={role.role_id} token={sessionToken} selected={outlook.scenario.scenario_id} pending={pending} onScenario={onScenario} /></div>
    <section className="roadmap-sdg-action surface" aria-labelledby="sdg-next-heading"><span className="role-next-icon"><Icon name="flag" /></span><div><h2 id="sdg-next-heading">{t("Connect your skills to purpose.")}</h2><p>{t("See how this pathway could contribute to the Sustainable Development Goals.")}</p></div><button id="open-sdg" className="button secondary" disabled={pending} onClick={onSdg}>{t("View SDG connections ")}<Icon name="arrow" /></button></section>
    <div className="roadmap-help">
      <PriorityEvidence evidence={outlook.learning_priority_evidence} labels={labels} />
      <PlanDetails plan={plan} courseStatus={courseStatus} profile={profile} />
      <div id="course-availability" className="caption"><Chip>{plan.selected_courses.length}{t(" verified courses in the full resource plan")}</Chip><p>{t("Curated modules use a selection of these courses and practical exercises. Additional provider links are optional choices.")}</p></div>
    </div>
  </section>;
}
