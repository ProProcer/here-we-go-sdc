import { t, useLanguage } from '../i18n';
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { json, request } from '../api';
import { cachedResult, resultKey, reuseResult } from '../resultCache';
import type { DependencyMap, Plan, RoadmapHorizon, RoleData } from '../types';
import CourseSources from './CourseSources';
import Select from './Select';
import { Chip, date, Disclosure, EmptyState, ExternalLink, Icon } from './ui';

const horizons: { id: RoadmapHorizon; label: string; duration: string }[] = [
  { id: 'short', label: 'Short term', duration: '1–3 months' },
  { id: 'standard', label: 'Standard', duration: '6 months' },
  { id: 'long', label: 'Long term', duration: '12 months' },
];

function Graph({ map, selected, onSelect }: { map: DependencyMap; selected: string | null; onSelect: (id: string) => void }) {
  const canvas = useRef<HTMLDivElement>(null);
  const marker = useId().replaceAll(':', '');
  const [drawing, setDrawing] = useState({ width: 1, height: 1, paths: [] as { key: string; path: string; basis: string }[] });
  const levels = [...new Set(map.nodes.map(node => node.level))].sort((a, b) => a - b);
  useLayoutEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const draw = () => {
      const bounds = element.getBoundingClientRect();
      const boxes = new Map([...element.querySelectorAll<HTMLButtonElement>('[data-module]')].map(node => [node.dataset.module, node.getBoundingClientRect()]));
      const paths = map.edges.flatMap(edge => {
        const a = boxes.get(edge.source), b = boxes.get(edge.target);
        if (!a || !b) return [];
        const x1 = a.x + a.width / 2 - bounds.x, y1 = a.bottom - bounds.y;
        const x2 = b.x + b.width / 2 - bounds.x, y2 = b.top - bounds.y - 5;
        const mid = (y1 + y2) / 2;
        return [{ key: `${edge.source}-${edge.target}`, basis: edge.basis, path: `M ${x1},${y1} C ${x1},${mid} ${x2},${mid} ${x2},${y2}` }];
      });
      setDrawing({ width: element.scrollWidth, height: element.scrollHeight, paths });
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    return () => observer.disconnect();
  }, [map]);
  return <div className="dependency-scroll" role="region" aria-label={t("Learning dependency graph")} tabIndex={0}>
    <div ref={canvas} className="dependency-canvas">
      <svg className="dependency-edges" width={drawing.width} height={drawing.height} aria-hidden="true"><defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#7da5ca" /></marker></defs>{drawing.paths.map(edge => <path key={edge.key} d={edge.path} className={edge.basis === 'course_prerequisite' ? 'confirmed-edge' : 'suggested-edge'} markerEnd={`url(#${marker})`} />)}</svg>
      {levels.map(level => <div className="dependency-layer" key={level} aria-label={t(`Learning stage ${level + 1}`)}>
        {map.nodes.filter(node => node.level === level).map(node => <button className={`module-card ${selected === node.node_id ? 'selected' : ''}`} key={node.node_id} data-module={node.node_id} aria-pressed={selected === node.node_id} aria-controls="module-detail" onClick={() => onSelect(node.node_id)}>
          <span className="module-stage">{t(level === 0 ? 'START HERE' : `BUILD ON STAGE ${level}`)}</span><strong>{t(node.title)}</strong>
          <span className="module-card-facts"><span><Icon name="clock" />{node.hours}{t(" h")}</span><span>{t(node.skills.length + node.embedded_skills.length)}{t(" skills together")}</span></span>
          <span className="module-card-bottom">{t("Week ")}{node.week_start}{t(node.week_end !== node.week_start ? `–${node.week_end}` : '')}<span>{t("View module ")}<Icon name="arrow" /></span></span>
        </button>)}
      </div>)}
    </div>
  </div>;
}

export default function DependencyRoadmap({ data, plan, token, revision, weeklyHours, onPace, horizon, onHorizon, onCurated }: {
  data: RoleData; plan: Plan; token: string | null; revision: number; weeklyHours: number;
  onPace: (hours: number) => void; horizon: RoadmapHorizon; onHorizon: (horizon: RoadmapHorizon) => void;
  onCurated: (map: DependencyMap | null) => void;
}) {
  const language = useLanguage();
  const [map, setMap] = useState<DependencyMap | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const details = useRef<HTMLElement>(null);
  const software = JSON.stringify(plan.selected_software_skill_ids || []);
  const cacheKey = resultKey(token, 'learning-map', [revision, data.match.role_id, data.outlook.scenario.scenario_id, horizon, weeklyHours, software, language, retry]);
  useEffect(() => {
    let cancelled = false;
    const saved = cachedResult<{ roadmap: DependencyMap }>(cacheKey);
    if (saved) {
      setMap(saved.roadmap); onCurated(saved.roadmap); setSelected(saved.roadmap.nodes[0]?.node_id || null);
      setLoading(false); setError(''); return;
    }
    setLoading(true); setError(''); setMap(null); onCurated(null);
    const timer = window.setTimeout(() => {
      void reuseResult(cacheKey, () => request<{ roadmap: DependencyMap }>('/pathways/dependencies', token, json('POST', {
        revision, role_id: data.match.role_id, scenario_id: data.outlook.scenario.scenario_id,
        selected_software_skill_ids: JSON.parse(software), horizon, weekly_hours: weeklyHours, language,
      })), result => result.roadmap.origin === 'ai_generated' ? 3600000 : 60000).then(result => {
        if (!cancelled) { setMap(result.roadmap); onCurated(result.roadmap); setSelected(result.roadmap.nodes[0]?.node_id || null); }
      }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not prepare your dependency map.'); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 300);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [cacheKey, data.match.role_id, data.outlook.scenario.scenario_id, horizon, weeklyHours, revision, software, token, language, retry, onCurated]);
  const module = map?.nodes.find(node => node.node_id === selected);
  const courses = new Map(plan.selected_courses.map(course => [course.course_id, course]));
  const paceOptions = [...new Set([2, 5, 10, 15, 20, weeklyHours])].sort((a, b) => a - b);
  const choose = (id: string) => {
    setSelected(id);
    if (window.innerWidth < 760) window.requestAnimationFrame(() => details.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  };
  return <section id="milestones" className="curated-roadmap" aria-labelledby="curated-heading">
    <div className="section-heading"><div><span className="mini-label">{t("FEWER GAPS. MORE FOCUS.")}</span><h2 id="curated-heading">{t("Your learning dependency map")}</h2></div></div>
    <div className="horizon-controls" aria-label={t("Planning period")}>{horizons.map(option => <button key={option.id} className={`horizon-button ${horizon === option.id ? 'selected' : ''}`} aria-pressed={horizon === option.id} onClick={() => onHorizon(option.id)}><strong>{t(option.label)}</strong><span>{t(option.duration)}</span></button>)}</div>
    <div className="dependency-toolbar"><p>{t("Follow the arrows. Skills in one module are learnt or practised together.")}</p><div className="pace-picker"><label htmlFor="roadmap-pace">{t("Weekly study pace")}</label><Select id="roadmap-pace" label={t("Weekly study pace")} value={String(weeklyHours)} onChange={value => onPace(Number(value))} options={paceOptions.map(hours => ({ value: String(hours), label: `${hours} hours / week` }))} /></div></div>
    {loading && <div className="dependency-loading" role="status"><svg className="spinner" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /></svg><div><strong>{t("Mapping your learning dependencies…")}</strong><p>{t("Grouping important gaps into practical modules.")}</p></div></div>}
    {error && <div className="feedback" role="alert"><p>{t(error)}</p><button className="button secondary" onClick={() => setRetry(value => value + 1)}>{t("Try again")}</button></div>}
    {map && <>
      {map.translation_status === 'unavailable' && <p className="caption" role="status">{t('Original English content shown. Translation is temporarily unavailable.')}</p>}
      <div id="roadmap-time-summary" className="curated-summary"><div><span className="mini-label">{t(horizons.find(option => option.id === map.horizon)?.duration)?.toUpperCase()}{t(" TARGET")}</span><strong id="roadmap-total-time">{t(`About ${map.estimated_weeks} weeks of learning`)}</strong><span>{map.planned_hours}{t(" h planned · ")}{map.nodes.length}{t(" focused modules · ")}{t(weeklyHours)}{t(" h/week")}</span></div><Chip>{t(map.origin === 'ai_generated' ? 'AI-curated' : 'Practice outline')}</Chip></div>
      {map.origin !== 'ai_generated' && map.nodes.length > 0 && <p className="caption dependency-fallback">{t(map.status === 'not_configured' ? 'AI curation is not configured. Showing an application-authored practice outline.' : 'AI curation is unavailable right now. Showing a practice outline.')} <button className="button secondary compact-button" onClick={() => setRetry(value => value + 1)}>{t("Retry AI mapping")}</button></p>}
      <p className="caption">{t(map.summary)}</p>
      {map.nodes.length ? <Graph map={map} selected={selected} onSelect={choose} /> : <EmptyState title={t("No remaining gaps")} compact>{t("Explore another role or optional software to create a learning focus.")}</EmptyState>}
      <div className="dependency-legend"><span><i />{t("Suggested learning order")}</span><span><i className="solid" />{t("Listed course prerequisite")}</span><small>{t("Independent branches can be studied alongside one another.")}</small></div>
      {module && <section id="module-detail" ref={details} className="module-detail surface" aria-labelledby="module-detail-title">
        <div className="section-heading"><div><span className="mini-label">{t("YOUR SELECTED MODULE")}</span><h3 id="module-detail-title">{t(module.title)}</h3></div><Chip>{module.hours}{t(" h estimate")}</Chip></div>
        <p>{t(module.objective)}</p>
        <div className="module-deliverable"><Icon name="flag" /><div><strong>{t("What you’ll make")}</strong><p>{t(module.deliverable)}</p></div></div>
        <div className="module-skills"><h4>{t("Focus skills")}</h4><div className="chips">{module.skills.map(skill => <Chip key={skill.skill_id}>{t(skill.label)}{t(skill.suggested_tool ? ' · suggested tool' : '')}</Chip>)}</div>
        {module.embedded_skills.length > 0 && <><h4>{t("Practised along the way")}</h4><div className="chips">{module.embedded_skills.map(skill => <Chip kind="confirmed" key={skill.skill_id}>{t(skill.label)}{t(skill.already_confirmed ? ' · build on this' : '')}</Chip>)}</div><p className="caption">{t("These support the project; they do not each need a separate course.")}</p></>}</div>
        <div className="module-course-list">{module.course_ids.map(id => {
          const course = courses.get(id);
          const covered = [...module.skills, ...module.embedded_skills].filter(skill => course?.skill_ids?.includes(skill.skill_id));
          return course ? <article className="module-course" key={id}><span className="mini-label">{t(covered.length > 1 ? 'ONE COURSE, MULTIPLE SKILLS' : 'COURSE FOR THIS MODULE')}</span><h4>{course.title}</h4><p>{course.provider} · {t(course.duration.display_text)} · {t(course.cost.access === 'paid' ? `${course.cost.currency} ${course.cost.amount}` : course.cost.access.replaceAll('_', ' '))}</p><div className="chips">{covered.map(skill => <Chip key={skill.skill_id}>{t(skill.label)}</Chip>)}</div><ExternalLink button url={course.course_url}>{t("View course")}</ExternalLink><small className="caption">{t("Provider record checked ")}{t(date(course.last_verified_at))}.</small></article> : null;
        })}</div>
        <p className="caption">{module.course_hours}{t(" h of listed courses + ")}{module.practice_hours}{t(" h suggested project practice. Practice time is an estimate.")}</p>
        {map.edges.some(edge => edge.target === module.node_id) && <Disclosure help title={t("Why these dependencies?")}><ul>{map.edges.filter(edge => edge.target === module.node_id).map(edge => <li key={edge.source}><strong>{t(map.nodes.find(node => node.node_id === edge.source)?.title)}:</strong> {t(edge.reason)} <small>{t(edge.basis === 'course_prerequisite' ? 'Listed prerequisite' : 'Suggested learning order')}</small></li>)}</ul></Disclosure>}
        <CourseSources skills={module.skills.map(skill => skill.label)} hasCourse={module.course_ids.length > 0} />
      </section>}
      <Disclosure help title={t(`How this plan was curated · ${map.deferred_skills.length} skills left for later`)}><p>{t("Important gaps are grouped around occupational tasks. Course coverage uses stored provider records; embedded project skills and learning-order suggestions are interpretations. The plan fits your selected time budget and does not change your fit score.")}</p><div className="chips">{map.deferred_skills.map(skill => <Chip key={skill.skill_id}>{t(skill.label)}</Chip>)}</div>{map.origin === 'ai_generated' && <p className="caption">{t("AI model: ")}{t(map.model)}{t(". Dependencies have not been human-reviewed.")}</p>}</Disclosure>
    </>}
  </section>;
}
