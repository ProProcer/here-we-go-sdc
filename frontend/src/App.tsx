import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { json, request } from './api';
import Loading from './components/Loading';
import RoleDrawer from './components/RoleDrawer';
import { Icon, type IconName } from './components/ui';
import Careers from './screens/Careers';
import Review, { type Preferences } from './screens/Review';
import Roadmap from './screens/Roadmap';
import Upload from './screens/Upload';
import type { CourseStatus, Evidence, Match, Outlook, Plan, Profile, ProfileResponse, ProfileSkill, Refresh, RoleData, RoleSummary, ScenarioId, Screen, Skill } from './types';

const stages: { id: Screen; label: string; short: string; icon: IconName; heading: string }[] = [
  { id: 'intake', label: 'Upload CV', short: 'Upload', icon: 'upload', heading: 'Your career journey' },
  { id: 'review', label: 'Review skills', short: 'Skills', icon: 'skills', heading: 'Review your skills' },
  { id: 'explore', label: 'Explore careers', short: 'Careers', icon: 'career', heading: 'Explore careers' },
  { id: 'detail', label: 'Learning roadmap', short: 'Roadmap', icon: 'path', heading: 'Your learning roadmap' },
];
const emptyPreferences: Preferences = { budget: '', hours: '', interests: '' };
function Brand({ mobile = false }: { mobile?: boolean }) {
  return <div className={`brand ${mobile ? 'mobile-brand' : ''}`} aria-label="ikiguy">
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path d="M16 16C5 16 5 4 11 4c5 0 5 7 5 12Z" fill="currentColor" opacity=".95" />
        <path d="M16 16C16 5 28 5 28 11c0 5-7 5-12 5Z" fill="currentColor" opacity=".75" />
        <path d="M16 16c11 0 11 12 5 12-5 0-5-7-5-12Z" fill="currentColor" opacity=".55" />
        <path d="M16 16C16 27 4 27 4 21c0-5 7-5 12-5Z" fill="currentColor" opacity=".75" />
        <circle cx="16" cy="16" r="2" fill="currentColor" />
      </svg>
    </span>
    <span className="brand-name">ikiguy<span className="brand-dot" aria-hidden="true">.</span></span>
  </div>;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('intake');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [removed, setRemoved] = useState(new Set<string>());
  const [added, setAdded] = useState(new Set<string>());
  const [target, setTarget] = useState<RoleSummary | null>(null);
  const [preferences, setPreferences] = useState(emptyPreferences);
  const [matches, setMatches] = useState<Match[]>([]);
  const [explored, setExplored] = useState(false);
  const [roleData, setRoleData] = useState<RoleData | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [courseStatus, setCourseStatus] = useState<CourseStatus | null>(null);
  const [selectedSoftware, setSelectedSoftware] = useState(new Set<string>());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState<{ label: string; upload: boolean } | null>(null);
  const [error, setError] = useState('');
  const pendingRef = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const pending = loading !== null;
  const confirmed = profile?.skills.filter(skill => skill.confirmation === 'confirmed' && !removed.has(skill.skill_id)) || [];
  const showError = useCallback((message: string) => setError(message), []);
  useLayoutEffect(() => {
    document.body.dataset.view = screen;
    window.scrollTo({ top: 0, behavior: 'instant' });
    const heading = document.querySelector<HTMLElement>(`#${screen} h1`);
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  }, [screen]);
  useEffect(() => {
    document.body.classList.toggle('is-busy', pending);
    return () => document.body.classList.remove('is-busy');
  }, [pending]);
  useEffect(() => { if (error && !drawerOpen) errorRef.current?.focus(); }, [error, drawerOpen]);
  useEffect(() => {
    document.body.dataset.sidebar = sidebarCollapsed ? 'collapsed' : 'expanded';
    return () => { delete document.body.dataset.sidebar; };
  }, [sidebarCollapsed]);

  async function action(label: string, callback: () => Promise<void>, upload = false) {
    if (pendingRef.current) return;
    pendingRef.current = true; setError(''); setLoading({ label, upload });
    try { await callback(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Something went wrong. Please try again.'); }
    finally { setLoading(null); pendingRef.current = false; }
  }
  function invalidate() {
    setMatches([]); setExplored(false); setRoleData(null); setPlan(null); setCourseStatus(null); setDrawerOpen(false); setSelectedSoftware(new Set());
  }
  async function acceptUpload(response: ProfileResponse, fileName: string | null = null) {
    if (token) await request('/profiles/current', token, { method: 'DELETE' });
    setToken(response.session_id); setRevision(response.revision); setProfile(response.profile);
    setRemoved(new Set()); setAdded(new Set()); setTarget(null); setPreferences(emptyPreferences);
    setUploadedFileName(fileName);
    invalidate(); setScreen('review');
  }
  function upload(file: File) {
    void action('Reading your CV', async () => {
      if (file.size > 2 * 1024 * 1024) throw new Error('Choose a CV smaller than 2 MB.');
      if (!/\.(pdf|docx|txt|jpe?g|png)$/i.test(file.name)) throw new Error('Choose a PDF, DOCX, TXT, JPG or PNG file.');
      await acceptUpload(await request<ProfileResponse>('/profiles/upload', token, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name) }, body: file,
      }), file.name);
    }, true);
  }
  function updateSkill(id: string, patch: Partial<ProfileSkill>) {
    if (pendingRef.current) return;
    setProfile(previous => previous && ({ ...previous, skills: previous.skills.map(skill => skill.skill_id === id ? { ...skill, ...patch, ...(patch.level !== undefined ? { level_assessment: null } : {}) } : skill) }));
    invalidate();
  }
  function removeSkill(id: string) {
    if (pendingRef.current) return;
    const next = new Set(removed);
    const restoring = next.delete(id);
    if (!restoring) next.add(id);
    else setProfile(previous => previous && ({ ...previous, skills: previous.skills.map(skill => skill.skill_id === id ? { ...skill, confirmation: 'unverified' } : skill) }));
    setRemoved(next); invalidate();
    const index = profile!.skills.findIndex(skill => skill.skill_id === id);
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-${restoring ? 'remove' : 'restore'}-skill="${index}"]`)?.focus());
  }
  function addSkill(skill: Skill) {
    if (pendingRef.current || !profile) return;
    const existing = profile.skills.some(item => item.skill_id === skill.skill_id);
    if (existing) { const next = new Set(removed); next.delete(skill.skill_id); setRemoved(next); }
    else {
      setProfile({ ...profile, skills: [...profile.skills, { ...skill, level: 'unknown', confirmation: 'unverified', evidence: ['Added by the user during CV review.'] }] });
      setAdded(previous => new Set(previous).add(skill.skill_id));
    }
    invalidate();
  }
  function reassessSkills() {
    void action('AI is assessing your skill levels', async () => {
      if (!profile) return;
      const response = await request<{ revision: number; profile: Profile }>('/profiles/assess', token, json('POST', {
        revision, skills: profile.skills,
      }));
      setRevision(response.revision); setProfile(response.profile); invalidate();
    });
  }
  function findMatches() {
    void action('Finding your career matches', async () => {
      if (!profile) return;
      if ((preferences.budget !== '' && (!Number.isFinite(Number(preferences.budget)) || Number(preferences.budget) < 0)) || (preferences.hours !== '' && (!Number.isFinite(Number(preferences.hours)) || Number(preferences.hours) < 0.5 || Number(preferences.hours) > 168))) throw new Error('Enter a nonnegative MYR budget and weekly hours between 0.5 and 168.');
      const response = await request<{ revision: number; profile: Profile }>('/profiles/current', token, json('PATCH', {
        revision, skills: confirmed, desired_role_id: target?.role_id || null,
        interests: preferences.interests.split(',').map(text => text.trim()).filter(Boolean),
        constraints: { budget_myr: preferences.budget === '' ? null : Number(preferences.budget), hours_per_week: preferences.hours === '' ? null : Number(preferences.hours) },
      }));
      setRevision(response.revision);
      // Keep excluded claims for local correction; only confirmed skills reach the API.
      setProfile({ ...profile, constraints: response.profile.constraints, interests: response.profile.interests, desired_role_id: response.profile.desired_role_id });
      const rows = confirmed.length ? (await request<{ matches: Match[] }>(`/matches?revision=${response.revision}`, token)).matches : [];
      setMatches(rows); setExplored(true); setScreen('explore');
    });
  }
  function openRole(id: string) {
    void action('Opening this career', async () => {
      const [detail, outlook, evidence, refresh, skillEvidence, roleImpacts] = await Promise.all([
        request<RoleData['detail']>(`/roles/${encodeURIComponent(id)}`, token), request<Outlook>(`/roles/${encodeURIComponent(id)}/outlook`, token),
        request<Evidence>(`/roles/${encodeURIComponent(id)}/evidence`, token), request<Refresh>('/evidence/status', token),
        request<RoleData['skillEvidence']>(`/roles/${encodeURIComponent(id)}/skill-evidence`, token).catch(() => null),
        request<RoleData['roleImpacts']>(`/roles/${encodeURIComponent(id)}/impacts`, token).catch(() => null),
      ]);
      const match = matches.find(role => role.role_id === id);
      if (!match) throw new Error('Choose a role from your current matches.');
      setRoleData({ match, detail, outlook, evidence, refresh, skillEvidence, roleImpacts }); setPlan(null); setSelectedSoftware(new Set()); setDrawerOpen(true);
    });
  }
  async function fetchPlan(data: RoleData, software = selectedSoftware) {
    const [result, status] = await Promise.all([request<{ plan: Plan }>('/pathways', token, json('POST', {
      revision, role_id: data.match.role_id, scenario_id: data.outlook.scenario.scenario_id, selected_software_skill_ids: [...software],
    })), request<CourseStatus>('/courses/status', token).catch(() => null)]);
    setCourseStatus(status);
    return result.plan;
  }
  function buildRoadmap() {
    if (!roleData || pendingRef.current) return;
    setDrawerOpen(false);
    void action('Preparing your learning path', async () => {
      if (!plan) setPlan(await fetchPlan(roleData));
      setScreen('detail');
    });
  }
  function changeScenario(id: ScenarioId) {
    if (!roleData || id === roleData.outlook.scenario.scenario_id || !roleData.outlook.available_scenarios.includes(id)) return;
    void action('Updating your learning priorities', async () => {
      const outlook = await request<Outlook>(`/roles/${encodeURIComponent(roleData.match.role_id)}/outlook?scenario_id=${id}`, token);
      const nextData = { ...roleData, outlook };
      const nextPlan = await fetchPlan(nextData);
      // Commit both together, leaving the existing roadmap intact on error.
      setRoleData(nextData); setPlan(nextPlan);
    });
  }
  function changeSoftware(id: string, checked: boolean) {
    if (!roleData || pendingRef.current) return;
    const next = new Set(selectedSoftware); if (checked) next.add(id); else next.delete(id);
    if (!plan) { setSelectedSoftware(next); return; }
    void action('Updating your learning path', async () => {
      const nextPlan = await fetchPlan(roleData, next); setSelectedSoftware(next); setPlan(nextPlan);
    });
  }
  function exportPlan() {
    if (!plan || !roleData || pendingRef.current) return;
    const blob = new Blob([JSON.stringify({ role_title: roleData.match.role_title, profile_is_fictional: true, plan }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'ikiguy-learning-plan.json'; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const enabled = { intake: true, review: !!profile, explore: explored, detail: !!plan };
  // Completion describes preparing each stage's output, not completing the learning itself.
  const completed = { intake: !!profile, review: explored, explore: !!plan, detail: !!plan };
  const stageIndex = stages.findIndex(stage => stage.id === screen);
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar" aria-label="Journey sidebar">
      <button className="sidebar-toggle" aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!sidebarCollapsed} aria-controls="journey-navigation" onClick={() => setSidebarCollapsed(value => !value)} title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}><Icon name={sidebarCollapsed ? 'panelOpen' : 'panelClose'} /></button>
      <Brand /><span className="nav-caption">YOUR NEXT CHAPTER</span>
      <nav id="journey-navigation" aria-label="Career journey">{stages.map((stage, index) => <button key={stage.id} className={`nav-item ${screen === stage.id ? 'active' : ''} ${completed[stage.id] ? 'completed' : ''}`} data-screen={stage.id} data-complete={completed[stage.id]} aria-label={stage.label} aria-description={completed[stage.id] ? (stage.id === 'detail' ? 'Roadmap ready' : 'Completed') : undefined} aria-current={screen === stage.id ? 'step' : undefined} title={sidebarCollapsed ? `${stage.label}${completed[stage.id] ? (stage.id === 'detail' ? ' — Roadmap ready' : ' — Completed') : ''}` : undefined} disabled={pending || !enabled[stage.id]} onClick={() => setScreen(stage.id)}><Icon name={stage.icon} /><span className="nav-full">{stage.label}</span><span className="nav-short">{stage.short}</span><span className="nav-status" aria-hidden="true">{!completed[stage.id] && <small>0{index + 1}</small>}</span></button>)}</nav>
      <div className="sidebar-bottom"><Icon name="spark" /><strong>Small steps.<br />New possibilities.</strong><span>Made for your next move.</span></div>
    </aside>
    <div className="workspace"><header className="topbar"><Brand mobile /><span id="breadcrumb">{stages[stageIndex].heading}</span></header>
      <main id="main" tabIndex={-1} aria-busy={pending || undefined}>
        <div id="feedback" ref={errorRef} className="feedback" role="alert" tabIndex={-1} hidden={!error || drawerOpen}>{error}</div>
        {pending && <Loading label={loading.label} upload={loading.upload} />}
        {screen === 'intake' && <Upload pending={pending} uploadedFileName={uploadedFileName} onReview={() => setScreen('review')} onUpload={upload} onSample={() => void action('Reading the sample CV', async () => acceptUpload(await request<ProfileResponse>('/profiles/sample', token, { method: 'POST' }), 'graduate.pdf'), true)} onManual={() => void action('Opening your skills', async () => acceptUpload(await request<ProfileResponse>('/profiles/manual', token, { method: 'POST' })))} />}
        {screen === 'review' && profile && <Review profile={profile} removed={removed} added={added} pending={pending} target={target} preferences={preferences} onSkill={updateSkill} onRemove={removeSkill} onConfirmAll={checked => { setProfile({ ...profile, skills: profile.skills.map(skill => removed.has(skill.skill_id) ? skill : { ...skill, confirmation: checked ? 'confirmed' : 'unverified' }) }); invalidate(); }} onAdd={addSkill} onTarget={role => { setTarget(role); invalidate(); }} onPreferences={next => { setPreferences(next); invalidate(); }} onContinue={findMatches} onError={showError} onAssess={reassessSkills} />}
        {screen === 'explore' && profile && <Careers matches={matches} profile={profile} confirmedCount={confirmed.length} target={target} pending={pending} onEdit={() => setScreen('review')} onOpen={openRole} />}
        {screen === 'detail' && profile && roleData && plan && <Roadmap sessionToken={token} data={roleData} plan={plan} courseStatus={courseStatus} profile={profile} pending={pending} onBack={() => setScreen('explore')} onDetails={() => setDrawerOpen(true)} onScenario={changeScenario} onExport={exportPlan} />}
      </main><footer>Adapted from O*NET® 31.0 · USDOL/ETA · <a href="https://www.onetcenter.org/license_db.html" target="_blank" rel="noopener noreferrer">CC BY 4.0</a> · No endorsement.</footer>
    </div>
    {roleData && profile && <RoleDrawer data={roleData} profile={profile} sessionToken={token} open={drawerOpen} pending={pending} loadingLabel={loading?.label || ''} error={error} selectedSoftware={selectedSoftware} hasPlan={!!plan} onClose={() => setDrawerOpen(false)} onSoftware={changeSoftware} onBuild={buildRoadmap} onReview={() => { setDrawerOpen(false); setScreen("review"); }} />}
  </>;
}
