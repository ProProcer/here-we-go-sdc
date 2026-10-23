import { useEffect, useState } from 'react';
import type { ExplainedSdg, SdgSummary } from '../types';
import { Chip, Disclosure, ExternalLink } from './ui';

const statusNames = { confirmed: 'In your profile', learning_goal: 'In your learning plan', role_requirement: 'Role requirement', needs_review: 'Review this skill' };

function GoalLink({ connection }: { connection: ExplainedSdg }) {
  const scope = connection.scope === 'role_application' ? 'Applying this career in practice' : connection.scope === 'career_preparation' ? 'Preparing for this career' : 'Developing and demonstrating this skill';
  return <div className="sdg-explanation">
    <div className="sdg-goal-heading"><span className={`sdg-goal sdg-${connection.sdg_id.replace('SDG ', '')}`}>{connection.sdg_id}</span><div><h4>{connection.goal_title}</h4><span className="caption">Target {connection.target_id} · {connection.target_label}</span></div></div>
    <p className="mini-label">{scope}</p><p>{connection.rationale}</p>
    <Disclosure title="Practical example & conditions"><p><strong>Put it into practice:</strong> {connection.application_example}</p><p>{connection.condition}</p><ExternalLink url={connection.evidence_url}>Read the official UN target</ExternalLink><p className="caption">Conditional application interpretation · {connection.contribution} contribution</p></Disclosure>
  </div>;
}

export default function SDGImpact({ summary }: { summary: SdgSummary }) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [showAll, setShowAll] = useState(false);
  useEffect(() => { setSearch(''); setFilter('all'); setShowAll(false); }, [summary.role_id]);
  const filtered = summary.skills.filter(skill => (!search || skill.label.toLowerCase().includes(search.toLowerCase())) && (filter === 'all' || skill.status === filter));
  const visible = showAll ? filtered : filtered.slice(0, 6);
  return <section id="sdg-impact" className="sdg-impact surface" aria-labelledby="sdg-impact-title">
    <div className="sdg-impact-heading"><div><span className="mini-label">CONNECT YOUR CAPABILITIES TO PURPOSE</span><h2 id="sdg-impact-title">How your pathway can contribute</h2></div><span id="sdg-coverage" className="caption">Career linked · {summary.mapped_skill_count}/{summary.skill_count} skills linked</span></div>
    <p>Explore how {summary.role_title} and your individual skills could support the Sustainable Development Goals through learning and practical work.</p>
    <div id="role-sdg-connections">{summary.role_connections.map(connection => <GoalLink key={`${connection.target_id}-${connection.scope}`} connection={connection} />)}</div>
    <div className="sdg-skills-heading"><h3>Your skills and their SDG links</h3><p className="caption">Includes skills in your profile, occupational requirements and planned learning. Confirmed skills keep their links; they are not treated as new gaps. A skill outside this role’s requirements is labelled separately.</p></div>
    <div className="sdg-skill-controls"><label htmlFor="sdg-skill-search">Find a skill<input id="sdg-skill-search" type="search" value={search} onChange={event => { setSearch(event.target.value); setShowAll(false); }} placeholder="Search skills" /></label><label htmlFor="sdg-skill-filter">Show<select id="sdg-skill-filter" value={filter} onChange={event => { setFilter(event.target.value); setShowAll(false); }}><option value="all">All skills</option><option value="confirmed">In your profile</option><option value="learning_goal">In your learning plan</option><option value="role_requirement">Role requirements</option><option value="needs_review">Needs your review</option></select></label></div>
    <p id="sdg-skill-count" className="caption">Showing {visible.length} of {filtered.length} {search || filter !== 'all' ? 'matching ' : ''}skills</p>
    <div id="skill-sdg-connections">{visible.map(skill => <details className="skill-sdg-row" key={skill.skill_id} data-sdg-skill={skill.skill_id}>
      <summary><span className="skill-sdg-label"><strong>{skill.label}</strong><small>{statusNames[skill.status]}{!skill.role_relevant ? ' · Role relevance not established' : ''}</small></span><span className="chips">{[...new Set(skill.connections.map(c => c.sdg_id))].map(goal => <Chip key={goal}>{goal}</Chip>)}</span><span className="skill-sdg-expand" aria-hidden="true">+</span></summary>
      <div className="skill-sdg-content">{skill.connections.map(connection => <GoalLink key={connection.target_id} connection={connection} />)}</div>
    </details>)}</div>
    {!filtered.length && <p>No skills match this search. Try another term or choose “All skills”.</p>}
    {filtered.length > 6 && <button id="show-sdg-skills" className="text-button" onClick={() => setShowAll(value => !value)}>{showAll ? 'Show fewer skills' : `Show all ${filtered.length} skills`}</button>}
    <Disclosure title="Use this evidence in your next conversation"><ul>
      <li><strong>Continuing in work:</strong> document a practical improvement and discuss development or internal mobility with your manager.</li>
      <li><strong>Starting your career:</strong> demonstrate a skill through a study project, volunteering or a portfolio example.</li>
      <li><strong>Changing careers:</strong> explain how an existing capability transfers to a task in your target role.</li>
      <li><strong>HR and L&D:</strong> agree development goals, support career transitions and evaluate work samples with the people involved.</li>
    </ul></Disclosure>
    <p className="caption sdg-interpretation-note">{summary.interpretation_note}</p>
  </section>;
}
