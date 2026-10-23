import type { ReviewedInterpretation, RoleData } from '../types';
import { Chip, date, Disclosure, EmptyState, ExternalLink } from './ui';

function Interpretation({ item }: { item: ReviewedInterpretation }) {
  return <><p>{item.rationale}</p><p className="caption"><ExternalLink url={item.source.source_url}>{item.source.publisher}</ExternalLink> · Published {date(item.source.published_at)}</p>
    <Disclosure title="Evidence & conditions">{item.supporting_findings.map((finding, index) => <div className="reviewed-finding" key={index}><Chip>{finding.evidence_type.replaceAll('_', ' ')}</Chip><p>{finding.claim}</p><blockquote>{finding.quote}</blockquote><p className="caption">Passage: {finding.reference.document_id} / {finding.reference.passage_id}</p></div>)}
      {item.applicability_conditions.length > 0 && <><h4>Applies when</h4><ul>{item.applicability_conditions.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
      {item.human_checks.length > 0 && <><h4>Limits to keep in mind</h4><ul>{item.human_checks.map((text, index) => <li key={index}>{text}</li>)}</ul></>}
    </Disclosure></>;
}
export default function ResearchEvidence({ data }: { data: RoleData }) {
  const skills = data.skillEvidence, impacts = data.roleImpacts;
  return <>
    <Disclosure title="Reviewed skill connections"><div id="shared-skill-evidence">
      {!skills ? <p role="status">Skill evidence is temporarily unavailable. Reopen this role to try again.</p> : <>
        {skills.approved_conditional_skill_evidence.length ? skills.approved_conditional_skill_evidence.map((item, index) => <article className="research-interpretation" key={`${item.skill_id}-${index}`}><h3>{item.skill_label}</h3><Chip>Reviewed · conditional</Chip><Interpretation item={item} /></article>) : <EmptyState compact symbol="book" title="No approved skill connections yet">{skills.pending_mapping_reviews > 0 ? `${skills.pending_mapping_reviews} proposed connections are waiting for a research reviewer to check and approve them.` : skills.unassessed_pairs > 0 ? `The research team has not yet assessed ${skills.unassessed_pairs} skill/article pairs relevant to this occupation. There are no completed connections awaiting approval here.` : 'No supported skill connections have been stored for this occupation.'} This is research coverage, not a judgment of your abilities. Approving your own CV skills does not approve research findings.</EmptyState>}
        <p className="caption">These connections describe selected research findings. They do not establish an occupational task effect or change your match score.</p>
        <Disclosure help title="Review coverage"><p>{skills.pending_mapping_reviews} connections awaiting review. {skills.unassessed_pairs} skill/article pairs not assessed. {skills.articles_awaiting_shared_review} articles awaiting shared review.</p></Disclosure>
      </>}
    </div></Disclosure>
    <Disclosure title="Reviewed role impacts"><div id="reviewed-role-impacts">
      {!impacts ? <p role="status">Role impact evidence is temporarily unavailable. Reopen this role to try again.</p> : <>
        {impacts.approved_conditional_role_impacts.length ? impacts.approved_conditional_role_impacts.map(item => <article className="research-interpretation" key={item.assessment_sha256}><Chip>Reviewed · conditional</Chip>{item.tasks.map(task => <h3 key={task.task_id}>{task.label}</h3>)}<Interpretation item={item} /></article>) : <EmptyState compact symbol="book" title="No approved role impacts yet">This occupation has no approved task-impact records to display. It does not mean the role is unaffected.</EmptyState>}
        <p className="caption">Conditional task relevance only. No measured employment, vacancy, or wage effect is claimed. Your skills and fit score stay unchanged.</p>
        <Disclosure help title="Review coverage"><p>{impacts.candidate_pairs} shortlisted role/article pairs; {impacts.unassessed_candidate_pairs} still unassessed. {impacts.skill_pairs_pending} skill/article pairs remain pending across the catalog. Coverage is limited to shortlisted roles and selected findings.</p></Disclosure>
      </>}
    </div></Disclosure>
  </>;
}
