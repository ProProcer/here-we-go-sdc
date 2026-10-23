import { useEffect, useRef } from 'react';
import ResearchEvidence from './ResearchEvidence';
import { Chip, date, Disclosure, EmptyState, ExternalLink, Icon, percent } from './ui';
import { matchingSkills } from '../screens/Careers';
import type { Profile, RoleData } from '../types';

export default function RoleDrawer({ data, profile, open, pending, loadingLabel, error, selectedSoftware, hasPlan, onClose, onSoftware, onBuild }: {
  data: RoleData; profile: Profile; open: boolean; pending: boolean; loadingLabel: string; error: string;
  selectedSoftware: Set<string>; hasPlan: boolean; onClose: () => void;
  onSoftware: (id: string, checked: boolean) => void; onBuild: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current?.close();
  }, [open]);
  useEffect(() => { if (open && error) errorRef.current?.focus(); }, [open, error]);
  const { match: role, outlook, evidence, refresh } = data;
  const breakdown = role.score_breakdown, coverage = breakdown.coverage;
  const weights = `Readiness weight: ${percent(breakdown.readiness_weight)}. Preference weight: ${percent(breakdown.preference_weight)}. Category familiarity does not establish proficiency in another tool. O*NET data does not establish Malaysian vacancies or hiring eligibility.`;
  return <dialog ref={dialog} id="role-drawer" className="role-drawer" aria-labelledby="drawer-title" onCancel={onClose} onClose={onClose} onClick={event => { if (event.target === event.currentTarget && event.clientX < event.currentTarget.getBoundingClientRect().left) onClose(); }}>
    <div className="drawer-header"><span className="mini-label">A POSSIBLE NEXT CHAPTER</span><button id="close-drawer" className="icon-button" aria-label="Close role details" onClick={onClose}><Icon name="close" /></button></div>
    <div className="drawer-content"><div id="drawer-feedback" ref={errorRef} className="feedback" role="alert" tabIndex={-1} hidden={!error}>{error}</div><span id="drawer-family" className="eyebrow">{role.family}</span><h2 id="drawer-title">{role.role_title}</h2><div id="drawer-fit" className="match-label"><strong>{role.fit_score.toFixed(2)}</strong> personal fit / 100 · Rank {role.rank}</div>
      <Disclosure title="About this occupation"><p id="role-description">{data.detail.role.description}</p></Disclosure>
      <h3>Why this match?</h3><div id="score-breakdown" className="score-breakdown">{([
        ['General skill coverage', coverage.general_coverage], ['Software category familiarity', coverage.software_group_coverage], ['Exact software coverage', coverage.software_exact_coverage],
      ] as const).map(([label, value]) => <div className="score-line" key={label}><span>{label}</span><strong>{percent(value)}</strong></div>)}</div>
      <Disclosure title="Matching skills"><div id="matched-skills" className="chips">{matchingSkills(role, profile).length ? matchingSkills(role, profile).map(skill => <details className="skill-proof" key={skill.skill_id}><summary><Chip kind="confirmed">{skill.label}</Chip><span className="caption">Evidence <span className="evidence-toggle" aria-hidden="true" /></span></summary><div>{skill.evidence.map((text, index) => <p key={index}>{text}</p>)}</div></details>) : <p>No confirmed requirements for this occupation yet.</p>}</div></Disclosure>
      <Disclosure title="Skills to explore"><p className="caption">These skills aren't confirmed in your profile. Missing evidence doesn't establish inability.</p><div id="gap-list">{role.missing_skills.length ? role.missing_skills.map(skill => <div className="gap-row" key={skill.skill_id}><div>{skill.label}<small>{skill.reason}</small></div><span>Importance {skill.importance.toFixed(2)}</span></div>) : <p>No general skill gaps remain.</p>}</div></Disclosure>
      <Disclosure title="Optional software to learn"><p className="caption">Choose tools for your roadmap. You don't need every tool used in an occupation.</p><div id="software-options" className="software-options">{role.software_learning_options.length ? role.software_learning_options.map((skill, index) => <label className="software-choice" key={skill.skill_id}><input type="checkbox" value={skill.skill_id} id={`software-${index}`} disabled={pending} checked={selectedSoftware.has(skill.skill_id)} onChange={event => onSoftware(skill.skill_id, event.target.checked)} /><span>{skill.label}{skill.group_familiarity_evidenced && <small>Related category familiarity is present.</small>}</span></label>) : <p>No unmatched in-demand software options for this role.</p>}</div></Disclosure>
      <Disclosure title="AI outlook & evidence"><h3 id="outlook-label">{outlook.baseline_label}</h3><div id="source-list">{outlook.sources.length ? outlook.sources.map(source => <div className="source-card" key={source.source_id}><h3><ExternalLink url={source.source_url}>{source.title}</ExternalLink></h3><p>{source.publisher} · Published {date(source.published_at)} · Retrieved {date(source.retrieved_at)}</p><p>{source.coverage} {source.limitations}</p>{outlook.signals.filter(signal => signal.source_id === source.source_id).map(signal => <p key={signal.signal_id}>{signal.claim}</p>)}</div>) : <EmptyState title="No reviewed evidence yet" compact symbol="book">An evidence-based AI outlook isn't available for this occupation. No employment trend is inferred.</EmptyState>}</div>
        <Disclosure title="Task context"><div id="task-list">{outlook.tasks.length ? outlook.tasks.map(task => <div className="task-card" key={task.task_id}><h3>{task.label}</h3><p>{task.interpretation}</p><Chip>{task.evidence_status.replaceAll('_', ' ')}</Chip>{task.mapping_basis && <Chip>Team interpretation · contextual</Chip>}{task.signal_ids.map(id => {
          const signal = outlook.signals.find(item => item.signal_id === id), source = outlook.sources.find(item => item.source_id === signal?.source_id);
          return source ? <p key={id}><ExternalLink url={source.source_url}>{source.title}</ExternalLink> · {date(source.published_at)}</p> : null;
        })}</div>) : <p>No task context available.</p>}</div></Disclosure>
        <Disclosure title="Source-to-skill reasoning"><div id="evidence-chains">{evidence.chains.length ? evidence.chains.map((chain, index) => <div className="source-card" key={index}><h3>{chain.task_label}</h3><p>{chain.finding.claim}</p><p><ExternalLink url={chain.source.source_url}>{chain.source.title}</ExternalLink> · Published {date(chain.source.published_at)} · Retrieved {date(chain.source.retrieved_at)}</p><p>Study period: {date(chain.reasoning.study_period_start)} to {date(chain.reasoning.study_period_end)}</p><Chip>{chain.reasoning.interpretation_status.replaceAll('_', ' ')}</Chip><p>{chain.reasoning.task_change}</p><p>Assumptions: {chain.reasoning.assumptions.join(' ')}</p><p>Human responsibilities: {chain.reasoning.human_responsibilities.join(' ')}</p>{chain.reasoning.skill_implications.map(item => <p key={item.skill_id}>{chain.skill_labels[item.skill_id]} · {item.direction.replaceAll('_', ' ')}: {item.rationale} {[...item.less_emphasis, ...item.more_emphasis].join(' ')}</p>)}<p>{chain.reasoning.limitations.join(' ')}</p></div>) : <p>Insufficient evidence for source-to-task-to-skill reasoning in this occupation.</p>}</div></Disclosure>
        <ResearchEvidence data={data} />
        <div id="refresh-status" className="caption">{refresh.refresh ? `${refresh.refresh.status}: ${refresh.refresh.message} Last attempt: ${date(refresh.refresh.attempted_at)}.` : 'No evidence refresh attempt recorded for this catalog.'}</div><div id="outlook-limitations" className="caption">{outlook.limitations.join(' ')}</div>
      </Disclosure>
      <Disclosure help title="Score & data limitations"><div id="match-warnings">{[...role.warnings, weights].join(' ')}</div></Disclosure>
    </div><div className="drawer-footer"><p id="drawer-busy" className="caption" role="status" hidden={!pending}>{loadingLabel}</p><button id="build-roadmap" className="button primary" disabled={pending} onClick={onBuild}>{hasPlan ? 'Return to my roadmap' : 'Build my roadmap'} <Icon name="arrow" /></button></div>
  </dialog>;
}
