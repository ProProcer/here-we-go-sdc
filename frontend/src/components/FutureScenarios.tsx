import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { date, Disclosure, ExternalLink } from './ui';
import type { ScenarioId } from '../types';

type Story = {
  scenario_id: 'moderate_ai_change' | 'rapid_ai_change'; headline: string; narrative: string;
  assumptions: string[]; task_changes: { task_id: string; task_label: string; possible_change: string; human_responsibility: string }[];
  practice_skill_label: string; practice_activity: string; uncertainties: string[]; source_ids: string[];
};
type Futures = {
  role_title: string; label: string; horizon: string; origin: string; generated_at: string | null; updating: boolean; update_unavailable: boolean;
  baseline: { summary: string; tasks: string[]; source_title: string; source_url: string; release: string };
  stories: Story[]; skill_comparison: { skill_id: string; label: string; baseline: number; moderate: number; rapid: number }[];
  shared_preparation: { skill_id: string; label: string; practice: string }[];
  sources: { article_id: string; title: string; publisher: string; source_url: string; published_at: string; fetched_at: string }[];
  priority_basis: string;
};

export default function FutureScenarios({ roleId, token, selected, pending, onScenario }: {
  roleId: string; token: string | null; selected: ScenarioId; pending: boolean; onScenario: (id: ScenarioId) => void;
}) {
  const [data, setData] = useState<Futures | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [allSkills, setAllSkills] = useState(false);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  useEffect(() => {
    let cancelled = false;
    setData(null); setError(''); setAllSkills(false);
    async function load() {
      try {
        const value = await request<Futures>(`/roles/${encodeURIComponent(roleId)}/futures`, selectedRef.current === 'baseline' ? null : token);
        if (!cancelled) { setData(value); setError(''); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Scenario stories could not be loaded.'); }
    }
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [roleId, token]);
  async function update() {
    setSubmitting(true); setError('');
    try { setData(await request<Futures>(`/roles/${encodeURIComponent(roleId)}/futures/refresh`, token, { method: 'POST' })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Story update is unavailable.'); }
    finally { setSubmitting(false); }
  }
  const story = data?.stories.find(item => item.scenario_id === selected);
  return <aside id="future-scenarios" className="scenario-card surface future-scenarios" aria-label="Plan under different AI adoption scenarios">
    <span className="mini-label">PLAN FOR YOUR NEXT STEP</span><h2>Choose your planning scenario</h2>
    <label className="scenario-select-label" htmlFor="scenario-select">Learning scenario</label>
    <select id="scenario-select" value={selected} disabled={pending} onChange={event => onScenario(event.target.value as ScenarioId)}>
      <option value="baseline">Baseline · current requirements</option>
      <option value="moderate_ai_change">Moderate AI adoption</option>
      <option value="rapid_ai_change">Rapid AI adoption</option>
    </select>
    <p id="future-disclaimer" className="caption">Moderate and rapid are hypothetical scenarios, not forecasts. They change learning emphasis, not your personal fit.</p>
    {error && <p role="alert" className="feedback">{error}</p>}
    {!data ? !error && <p role="status">Loading planning context…</p> : <>
      {selected === 'baseline' && <div id="future-baseline-context">
        <h3>Build from where you are today.</h3><p>Start with the activities that matter to your next role or development goal. Use work, study or project examples to demonstrate what you can do.</p>
        <Disclosure title="Current role context"><p>{data.baseline.summary}</p><p className="caption"><ExternalLink url={data.baseline.source_url}>{data.baseline.source_title}</ExternalLink> · Release {data.baseline.release}. Occupational requirements do not measure local hiring demand.</p></Disclosure>
      </div>}
      {story && <article className="future-story single" data-future-scenario={story.scenario_id}>
        <div id="scenario-note" className="scenario-note">HYPOTHETICAL SCENARIO · Not a forecast</div>
        <h3>{story.headline}</h3><p>{story.narrative}</p>
        <p><strong>Assumption:</strong> {story.assumptions[0]}</p>
        <Disclosure title="Possible task changes & human responsibilities">{story.task_changes.map(task => <div className="future-task" key={task.task_id}><h4>{task.task_label}</h4><p><strong>Possible change:</strong> {task.possible_change}</p><p><strong>Human responsibility:</strong> {task.human_responsibility}</p></div>)}</Disclosure>
        <h4>How you could prepare</h4><p><strong>{story.practice_skill_label}:</strong> {story.practice_activity}</p>
        <Disclosure title="What could change this future?"><ul>{story.uncertainties.map(text => <li key={text}>{text}</li>)}</ul><p>{data.horizon}</p><h4>Additional assumptions</h4><ul>{story.assumptions.slice(1).map(text => <li key={text}>{text}</li>)}</ul></Disclosure>
        <p className="caption">{data.origin === 'ai_generated' ? `AI-generated explanation · Created ${date(data.generated_at)} · Not human reviewed.` : 'Application-authored illustration.'}</p>
      </article>}
      <Disclosure id="future-comparison" title="Compare all three scenarios">
        <div id="future-skill-comparison"><h3 id="priority-comparison">How priorities change</h3><p className="caption">Illustrative weights, not probabilities or skill deficits. The roadmap applies these priorities to the skills in your plan.</p>
          <div className="future-table-scroll"><table><thead><tr><th scope="col">Skill</th><th scope="col">Baseline</th><th scope="col">Moderate</th><th scope="col">Rapid</th></tr></thead><tbody>{(allSkills ? data.skill_comparison : data.skill_comparison.slice(0, 6)).map(row => <tr key={row.skill_id}><th scope="row">{row.label}</th><td>{row.baseline.toFixed(2)}</td><td className={selected === 'moderate_ai_change' ? 'current' : ''}>{row.moderate.toFixed(2)}</td><td className={selected === 'rapid_ai_change' ? 'current' : ''}>{row.rapid.toFixed(2)}</td></tr>)}</tbody></table></div>
          <div className="future-actions">
            {data.skill_comparison.length > 6 && <button className="text-button" onClick={() => setAllSkills(value => !value)}>{allSkills ? 'Show fewer skills' : `Show all ${data.skill_comparison.length} affected skill priorities`}</button>}
            {selected !== 'baseline' && <button id="future-baseline" className="text-button" disabled={pending} onClick={() => onScenario('baseline')}>Return roadmap to baseline</button>}
          </div>
          <Disclosure title="How these estimates are set"><p>{data.priority_basis}</p><p>General scenarios add an illustrative 0.08 under moderate adoption or 0.16 under rapid adoption to selected checking, learning and communication priorities, capped at 1.00. Role-specific policy assumptions are shown with the scenario. AI explains the scenarios; numeric adjustments follow the application policy.</p></Disclosure>
        </div>
      </Disclosure>
      <Disclosure title="Preparation useful across scenarios"><div id="shared-future-preparation"><p className="caption">Use these activities to build or demonstrate capabilities you already have.</p>{data.shared_preparation.map(skill => <div key={skill.skill_id}><h4>{skill.label}</h4><p>{skill.practice}</p></div>)}</div></Disclosure>
      {selected !== 'baseline' && <Disclosure title="Story sources & updates">
        <p className="caption">Research provides background. Future adoption and task changes remain assumptions. No outcome probabilities are estimated.</p>
        {data.sources.length ? data.sources.filter(source => story?.source_ids.includes(source.article_id)).map(source => <p key={source.article_id}><ExternalLink url={source.source_url}>{source.title}</ExternalLink> · {source.publisher} · Published {date(source.published_at)} · Fetched {date(source.fetched_at)}.</p>) : <p>These illustrations use occupational tasks and authored adoption assumptions.</p>}
        {data.update_unavailable && <p>The latest update is unavailable. Your complete illustration remains available.</p>}
        <button className="text-button" disabled={!token || submitting || data.updating} onClick={() => void update()}>{submitting || data.updating ? 'Updating explanation…' : 'Update scenario explanation'}</button>
      </Disclosure>}
    </>}
  </aside>;
}
