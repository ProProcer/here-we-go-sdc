import { t } from '../i18n';
import type { PriorityEvidence as Evidence } from '../types';
import { Disclosure } from './ui';

const statuses: Record<string, string> = {
  applied: 'Reviewed adjustment', insufficient_independent_evidence: 'More independent evidence needed',
  conflicting_evidence: 'Conflicting evidence',
};
export default function PriorityEvidence({ evidence, labels }: { evidence: Evidence | undefined; labels: Map<string, string> }) {
  return <Disclosure help title={t("Why these learning priorities?")}><div id="priority-evidence">
    {!evidence ? <p>{t("Evidence-adjustment details are unavailable. No additional evidence-based adjustment is claimed here.")}</p> : <>
      <p>{t("Priorities start with occupational requirements. Hypothetical scenarios and separately reviewed research adjustments are explained independently. They do not change your skills or career fit.")}</p>
      {!evidence.decisions.length ? <p>{t("No approved research adjustments are available for this role. Its learning priorities use occupational requirements and the selected scenario.")}</p> : evidence.decisions.map(decision => <article className="research-interpretation" key={decision.skill_id}><h3>{t(labels.get(decision.skill_id) || decision.skill_id)}</h3><p>{t(statuses[decision.status] || decision.status.replaceAll('_', ' '))}{t(" · Research adjustment ")}{t(decision.adjustment > 0 ? '+' : '')}{decision.adjustment.toFixed(3)}</p><p>{t(decision.independent_studies)}{t(" independent studies · ")}{t(decision.publishers)}{t(" publishers")}</p><p className="caption">{t("Scenario adjustment: ")}{(decision.scenario_adjustment ?? 0).toFixed(3)}{t(". Effective research adjustment after bounds: ")}{(decision.effective_evidence_adjustment ?? decision.adjustment).toFixed(3)}.</p><Disclosure title={t("Decision references")}><ul>{decision.contributing_assessment_ids.map(id => <li className="review-reference" key={id}>{t(id)}</li>)}</ul>{decision.excluded_assessment_ids.length > 0 && <p>{decision.excluded_assessment_ids.length}{t(" assessment records excluded from this decision.")}</p>}</Disclosure></article>)}
      <Disclosure title={t("Policy & limitations")}><p>{t("Policy: ")}{t(evidence.policy_version)}{t(". Maximum research adjustment: ±")}{evidence.maximum_adjustment.toFixed(2)}{t(". This is an application policy, not an empirically calibrated forecast.")}</p>{evidence.rejected_assessments.length > 0 && <><p>{evidence.rejected_assessments.length}{t(" assessments could not be used:")}</p><ul>{evidence.rejected_assessments.map(item => <li key={item.assessment_id}>{t(item.reason)}</li>)}</ul></>}</Disclosure>
    </>}
  </div></Disclosure>;
}
