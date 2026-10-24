import { t } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import Select from './Select';
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
  return <aside id="future-scenarios" className="scenario-card surface future-scenarios" aria-label={t("Plan under different AI adoption scenarios")}>
    <span className="mini-label">{t("PLAN FOR YOUR NEXT STEP")}</span><h2>{t("Choose your planning scenario")}</h2>
    <div className="scenario-picker"><label className="scenario-select-label" htmlFor="scenario-select">{t("Learning scenario")}</label>
    <Select id="scenario-select" label={t("Learning scenario")} value={selected} disabled={pending} onChange={value => onScenario(value as ScenarioId)} options={[
      { value: 'baseline', label: 'Baseline · current requirements' },
      { value: 'moderate_ai_change', label: 'Moderate AI adoption' },
      { value: 'rapid_ai_change', label: 'Rapid AI adoption' },
    ]} /></div>
    <p id="future-disclaimer" className="caption">{t("Moderate and rapid are hypothetical scenarios, not forecasts. They change learning emphasis, not your personal fit.")}</p>
    {error && <p role="alert" className="feedback">{t(error)}</p>}
    {!data ? !error && <p role="status">{t("Loading planning context…")}</p> : <>
      {selected === 'baseline' && <div id="future-baseline-context">
        <h3>{t("Build from where you are today.")}</h3><p>{t("Start with the activities that matter to your next role or development goal. Use work, study or project examples to demonstrate what you can do.")}</p>
        <Disclosure title={t("Current role context")}><p>{t(data.baseline.summary)}</p><p className="caption"><ExternalLink url={data.baseline.source_url}>{t(data.baseline.source_title)}</ExternalLink>{t(" · Release ")}{t(data.baseline.release)}{t(". Occupational requirements do not measure local hiring demand.")}</p></Disclosure>
      </div>}
      {story && <article className="future-story single" data-future-scenario={story.scenario_id}>
        <div id="scenario-note" className="scenario-note">{t("HYPOTHETICAL SCENARIO · Not a forecast")}</div>
        <h3>{t(story.headline)}</h3><p>{t(story.narrative)}</p>
        <p><strong>{t("Assumption:")}</strong> {t(story.assumptions[0])}</p>
        <Disclosure title={t("Possible task changes & human responsibilities")}>{story.task_changes.map(task => <div className="future-task" key={task.task_id}><h4>{t(task.task_label)}</h4><p><strong>{t("Possible change:")}</strong> {t(task.possible_change)}</p><p><strong>{t("Human responsibility:")}</strong> {t(task.human_responsibility)}</p></div>)}</Disclosure>
        <h4>{t("How you could prepare")}</h4><p><strong>{t(story.practice_skill_label)}:</strong> {t(story.practice_activity)}</p>
        <Disclosure title={t("What could change this future?")}><ul>{story.uncertainties.map(text => <li key={text}>{t(text)}</li>)}</ul><p>{t(data.horizon)}</p><h4>{t("Additional assumptions")}</h4><ul>{story.assumptions.slice(1).map(text => <li key={text}>{t(text)}</li>)}</ul></Disclosure>
        <p className="caption">{t(data.origin === 'ai_generated' ? `AI-generated explanation · Created ${date(data.generated_at)} · Not human reviewed.` : 'Application-authored illustration.')}</p>
      </article>}
      <Disclosure id="future-comparison" title={t("Compare all three scenarios")}>
        <div id="future-skill-comparison"><h3 id="priority-comparison">{t("How priorities change")}</h3><p className="caption">{t("Illustrative weights, not probabilities or skill deficits. The roadmap applies these priorities to the skills in your plan.")}</p>
          <div className="future-table-scroll"><table><thead><tr><th scope="col">{t("Skill")}</th><th scope="col">{t("Baseline")}</th><th scope="col">{t("Moderate")}</th><th scope="col">{t("Rapid")}</th></tr></thead><tbody>{(allSkills ? data.skill_comparison : data.skill_comparison.slice(0, 6)).map(row => <tr key={row.skill_id}><th scope="row">{t(row.label)}</th><td>{row.baseline.toFixed(2)}</td><td className={selected === 'moderate_ai_change' ? 'current' : ''}>{row.moderate.toFixed(2)}</td><td className={selected === 'rapid_ai_change' ? 'current' : ''}>{row.rapid.toFixed(2)}</td></tr>)}</tbody></table></div>
          <div className="future-actions">
            {data.skill_comparison.length > 6 && <button className="text-button" onClick={() => setAllSkills(value => !value)}>{t(allSkills ? 'Show fewer skills' : `Show all ${data.skill_comparison.length} affected skill priorities`)}</button>}
            {selected !== 'baseline' && <button id="future-baseline" className="text-button" disabled={pending} onClick={() => onScenario('baseline')}>{t("Return roadmap to baseline")}</button>}
          </div>
          <Disclosure title={t("How these estimates are set")}><p>{t(data.priority_basis)}</p><p>{t("General scenarios add an illustrative 0.08 under moderate adoption or 0.16 under rapid adoption to selected checking, learning and communication priorities, capped at 1.00. Role-specific policy assumptions are shown with the scenario. AI explains the scenarios; numeric adjustments follow the application policy.")}</p></Disclosure>
        </div>
      </Disclosure>
      <Disclosure title={t("Preparation useful across scenarios")}><div id="shared-future-preparation"><p className="caption">{t("Use these activities to build or demonstrate capabilities you already have.")}</p>{data.shared_preparation.map(skill => <div key={skill.skill_id}><h4>{t(skill.label)}</h4><p>{t(skill.practice)}</p></div>)}</div></Disclosure>
      {selected !== 'baseline' && <Disclosure title={t("Story sources & updates")}>
        <p className="caption">{t("Research provides background. Future adoption and task changes remain assumptions. No outcome probabilities are estimated.")}</p>
        {data.sources.length ? data.sources.filter(source => story?.source_ids.includes(source.article_id)).map(source => <p key={source.article_id}><ExternalLink url={source.source_url}>{t(source.title)}</ExternalLink> · {t(source.publisher)}{t(" · Published ")}{t(date(source.published_at))}{t(" · Fetched ")}{t(date(source.fetched_at))}.</p>) : <p>{t("These illustrations use occupational tasks and authored adoption assumptions.")}</p>}
        {data.update_unavailable && <p>{t("The latest update is unavailable. Your complete illustration remains available.")}</p>}
        <button className="text-button" disabled={!token || submitting || data.updating} onClick={() => void update()}>{t(submitting || data.updating ? 'Updating explanation…' : 'Update scenario explanation')}</button>
      </Disclosure>}
    </>}
  </aside>;
}
