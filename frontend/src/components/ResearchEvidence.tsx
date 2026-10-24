import { t } from '../i18n';
import type { ReviewedInterpretation, RoleData } from '../types';
import { Chip, date, Disclosure, EmptyState, ExternalLink } from './ui';

function Interpretation({ item }: { item: ReviewedInterpretation }) {
  return <><p>{t(item.rationale)}</p><p className="caption"><ExternalLink url={item.source.source_url}>{t(item.source.publisher)}</ExternalLink>{t(" · Published ")}{t(date(item.source.published_at))}</p>
    <Disclosure title={t("Evidence & conditions")}>{item.supporting_findings.map((finding, index) => <div className="reviewed-finding" key={index}><Chip>{t(finding.evidence_type.replaceAll('_', ' '))}</Chip><p>{t(finding.claim)}</p><blockquote>{t(finding.quote)}</blockquote><p className="caption">{t("Passage: ")}{t(finding.reference.document_id)} / {t(finding.reference.passage_id)}</p></div>)}
      {item.applicability_conditions.length > 0 && <><h4>{t("Applies when")}</h4><ul>{item.applicability_conditions.map((text, index) => <li key={index}>{t(text)}</li>)}</ul></>}
      {item.human_checks.length > 0 && <><h4>{t("Limits to keep in mind")}</h4><ul>{item.human_checks.map((text, index) => <li key={index}>{t(text)}</li>)}</ul></>}
    </Disclosure></>;
}
export default function ResearchEvidence({ data }: { data: RoleData }) {
  const skills = data.skillEvidence, impacts = data.roleImpacts;
  return <>
    <Disclosure title={t("Reviewed skill connections")}><div id="shared-skill-evidence">
      {!skills ? <p role="status">{t("Skill evidence is temporarily unavailable. Reopen this role to try again.")}</p> : <>
        {skills.approved_conditional_skill_evidence.length ? skills.approved_conditional_skill_evidence.map((item, index) => <article className="research-interpretation" key={`${item.skill_id}-${index}`}><h3>{t(item.skill_label)}</h3><Chip>{t("Reviewed · conditional")}</Chip><Interpretation item={item} /></article>) : <EmptyState compact symbol="book" title={t("No approved skill connections yet")}>{t(skills.pending_mapping_reviews > 0 ? `${skills.pending_mapping_reviews} proposed connections are waiting for a research reviewer to check and approve them.` : skills.unassessed_pairs > 0 ? `The research team has not yet assessed ${skills.unassessed_pairs} skill/article pairs relevant to this occupation. There are no completed connections awaiting approval here.` : 'No supported skill connections have been stored for this occupation.')}{t(" This is research coverage, not a judgment of your abilities. Approving your own CV skills does not approve research findings.")}</EmptyState>}
        <p className="caption">{t("These connections describe selected research findings. They do not establish an occupational task effect or change your match score.")}</p>
        <Disclosure help title={t("Review coverage")}><p>{t(skills.pending_mapping_reviews)}{t(" connections awaiting review. ")}{t(skills.unassessed_pairs)}{t(" skill/article pairs not assessed. ")}{t(skills.articles_awaiting_shared_review)}{t(" articles awaiting shared review.")}</p></Disclosure>
      </>}
    </div></Disclosure>
    <Disclosure title={t("Reviewed role impacts")}><div id="reviewed-role-impacts">
      {!impacts ? <p role="status">{t("Role impact evidence is temporarily unavailable. Reopen this role to try again.")}</p> : <>
        {impacts.approved_conditional_role_impacts.length ? impacts.approved_conditional_role_impacts.map(item => <article className="research-interpretation" key={item.assessment_sha256}><Chip>{t("Reviewed · conditional")}</Chip>{item.tasks.map(task => <h3 key={task.task_id}>{t(task.label)}</h3>)}<Interpretation item={item} /></article>) : <EmptyState compact symbol="book" title={t("No approved role impacts yet")}>{t("This occupation has no approved task-impact records to display. It does not mean the role is unaffected.")}</EmptyState>}
        <p className="caption">{t("Conditional task relevance only. No measured employment, vacancy, or wage effect is claimed. Your skills and fit score stay unchanged.")}</p>
        <Disclosure help title={t("Review coverage")}><p>{t(impacts.candidate_pairs)}{t(" shortlisted role/article pairs; ")}{t(impacts.unassessed_candidate_pairs)}{t(" still unassessed. ")}{t(impacts.skill_pairs_pending)}{t(" skill/article pairs remain pending across the catalog. Coverage is limited to shortlisted roles and selected findings.")}</p></Disclosure>
      </>}
    </div></Disclosure>
  </>;
}
