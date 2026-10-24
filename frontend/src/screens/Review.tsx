import { t } from '../i18n';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Search from '../components/Search';
import Select from '../components/Select';
import { Chip, Disclosure, EmptyState, Icon } from '../components/ui';
import type { Profile, ProfileSkill, RoleSummary, Skill } from '../types';

export interface Preferences { budget: string; hours: string; interests: string }
export default function Review({ profile, removed, added, pending, target, preferences, onSkill, onRemove, onConfirmAll, onAdd, onTarget, onPreferences, onContinue, onError, onAssess }: {
  profile: Profile; removed: Set<string>; added: Set<string>; pending: boolean; target: RoleSummary | null;
  preferences: Preferences; onSkill: (id: string, patch: Partial<ProfileSkill>) => void;
  onRemove: (id: string) => void; onConfirmAll: (checked: boolean) => void; onAdd: (skill: Skill) => void;
  onTarget: (role: RoleSummary | null) => void; onPreferences: (preferences: Preferences) => void;
  onContinue: () => void; onError: (message: string) => void;
  onAssess: () => void;
}) {
  const active = profile.skills.filter(skill => !removed.has(skill.skill_id));
  const confirmed = active.filter(skill => skill.confirmation === 'confirmed').length;
  const missingLevels = active.filter(skill => skill.confirmation === 'confirmed' && skill.level === 'unknown');
  const nextMissingLevel = missingLevels.find(skill => skill.skill_id.startsWith('skill:onet_')) || missingLevels[0];
  const [step, setStep] = useState<'skills' | 'direction'>('skills');
  const [manualLevels, setManualLevels] = useState(new Set<string>());
  const selectAll = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const circumference = 2 * Math.PI * 34;
  function openLevel(skill: ProfileSkill) {
    const index = profile.skills.indexOf(skill);
    setManualLevels(previous => new Set(previous).add(skill.skill_id));
    requestAnimationFrame(() => {
      const input = document.getElementById(`skill-${index}`);
      const evidence = input?.closest('.skill-row')?.querySelector<HTMLDetailsElement>('.cv-evidence');
      if (evidence) evidence.open = true;
      const control = document.getElementById(`level-${index}`);
      control?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      control?.focus({ preventScroll: true });
    });
  }
  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = confirmed > 0 && confirmed < active.length;
  }, [confirmed, active.length]);
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
    heading.current?.focus({ preventScroll: true });
  }, [step]);
  const groups = [
    { title: 'Tools & technologies', skills: active.filter(skill => !skill.skill_id.startsWith('skill:onet_')) },
    { title: 'Core skills', skills: active.filter(skill => skill.skill_id.startsWith('skill:onet_')) },
    { title: 'Removed skills', skills: profile.skills.filter(skill => removed.has(skill.skill_id)) },
  ];
  return <section id="review" className="screen">
    <div className="page-heading"><div><span className="eyebrow">{t("YOUR EXPERIENCE, IN YOUR WORDS")}</span><h1 ref={heading} tabIndex={-1}>{t(step === 'skills' ? "Let's review your skills." : 'Where would you like to go?')}</h1><p className="page-intro">{t(step === 'skills' ? 'Confirm what fits. Add anything we missed.' : 'Choose a career goal, or explore with an open mind.')}</p></div></div>
    <ol className="review-steps" aria-label={t("Profile review")}><li aria-current={step === 'skills' ? 'step' : undefined}><span>{step === 'direction' ? <Icon name="check" /> : '1'}</span>{t("Review skills")}</li><li aria-current={step === 'direction' ? 'step' : undefined}><span>2</span>{t("Your direction ")}<small>{t("Optional")}</small></li></ol>
    <div className="review-layout"><div className="review-main" hidden={step !== 'skills'}>
      {profile.assessment_status && <div id="ai-assessment-status" className="assessment-status surface" role="status"><div><span className="mini-label">{t("AI SKILL ASSESSMENT")}</span><p>{t(profile.assessment_status.message)}</p></div>{profile.assessment_status.status !== 'completed' && <button id="retry-assessment" className="button secondary" disabled={pending} onClick={() => { setManualLevels(new Set()); onAssess(); }}>{t("Retry AI assessment")}</button>}</div>}
      <div className="skill-overview"><div><span>{t("Your starting point")}</span><strong id="skill-count">{t(`${active.length} skills to make your own`)}</strong></div><div className="skill-confirmation"><div className="skill-count-circle" role="progressbar" aria-label={t("Skill confirmation progress")} aria-valuemin={0} aria-valuemax={active.length || 1} aria-valuenow={confirmed} aria-valuetext={t(`${confirmed} of ${active.length} skills confirmed`)}><svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="34" fill="none" stroke="#D1E5F7" strokeWidth="6" /><circle className="confirmation-ring" cx="40" cy="40" r="34" fill="none" stroke="var(--blue)" strokeWidth="6" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - (active.length ? confirmed / active.length : 0))} transform="rotate(-90 40 40)" /></svg><strong id="confirmed-count">{t(confirmed)}</strong></div><span>{t("confirmed")}</span></div></div>
      <div className="section-heading"><h2>{t("Your skills")}</h2><label className="confirm-all-control"><input ref={selectAll} id="confirm-all" type="checkbox" disabled={pending || active.length === 0} checked={active.length > 0 && confirmed === active.length} onChange={event => onConfirmAll(event.target.checked)} /><span>{t("Confirm all skills")}</span></label></div>
      {nextMissingLevel && <div id="missing-levels-notice" className="missing-levels-notice" role="status"><p>{t(`${missingLevels.length} confirmed skills still need a level.`)}</p><button id="set-next-level" className="button secondary compact-button" disabled={pending} onClick={() => openLevel(nextMissingLevel)}>{t('Set next skill level')}</button></div>}
      <div id="skill-list">{profile.skills.length ? groups.map(group => group.skills.length > 0 && <div className="skill-group" key={group.title}><h3 className="skill-group-title">{t(group.title)} <Chip>{group.skills.length}</Chip></h3><div className="skill-group-rows">{group.skills.map(skill => {
        const index = profile.skills.indexOf(skill), isRemoved = removed.has(skill.skill_id), isConfirmed = skill.confirmation === 'confirmed';
        return <div className={`skill-row ${isRemoved ? 'removed' : ''}`} key={skill.skill_id}>
          <input id={`skill-${index}`} type="checkbox" data-skill-index={index} disabled={pending || isRemoved} checked={isConfirmed && !isRemoved} onChange={event => onSkill(skill.skill_id, { confirmation: event.target.checked ? 'confirmed' : 'unverified' })} />
          <div><div className="skill-name"><label htmlFor={`skill-${index}`}>{t(skill.label)}</label>{isRemoved ? <Chip kind="removed">{t("Removed")}</Chip> : <>{added.has(skill.skill_id) && <Chip kind="added">{t("Added by you")}</Chip>}{skill.level_assessment && <Chip>{t("AI estimate: ")}{t(skill.level === "unknown" ? "insufficient evidence" : skill.level)}</Chip>}<Chip kind={isConfirmed ? 'confirmed' : 'unconfirmed'}>{t(isConfirmed ? 'Confirmed' : 'To review')}</Chip>{skill.level === 'unknown' && <button className="button secondary compact-button" data-set-level={index} disabled={pending} onClick={() => openLevel(skill)}>{t('Set level')}</button>}</>}</div>
            {!isRemoved && !added.has(skill.skill_id) && !skill.level_assessment && <p className="caption">{t("AI level: not assessed. See the assessment status above.")}</p>}{!isRemoved && <details className="cv-evidence"><summary>{t("View CV evidence ")}<Icon name="chevron" /></summary><div className="cv-evidence-content"><div className="cv-evidence-passages">{skill.evidence.length ? skill.evidence.map((text, i) => <p key={i}>{t(text)}</p>) : <p>{t("No CV passage is available. You can still confirm this skill.")}</p>}</div><div className="skill-level-field">{skill.level_assessment && <p className="caption"><Chip>{t("AI estimate · ")}{t(skill.level_assessment.confidence)}{t(" confidence")}</Chip> {t(skill.level_assessment.rationale)}</p>}{added.has(skill.skill_id) || manualLevels.has(skill.skill_id) ? <><label htmlFor={`level-${index}`}>{t("Your skill level")}</label><Select id={`level-${index}`} label={t("Your skill level")} disabled={pending} value={skill.level} onChange={value => onSkill(skill.skill_id, { level: value as ProfileSkill['level'] })} options={(['unknown', 'beginner', 'intermediate', 'advanced'] as const).map(level => ({ value: level, label: level === 'unknown' ? 'Not specified' : level[0].toUpperCase() + level.slice(1) }))} /></> : <><span className="mini-label">{t("AI-assessed level")}</span><strong id={`level-${index}`} className="automatic-level">{t(skill.level_assessment ? (skill.level === 'unknown' ? 'Not enough evidence to estimate' : skill.level[0].toUpperCase() + skill.level.slice(1)) : 'Not assessed — AI unavailable')}</strong><button id={`correct-level-${index}`} className="text-button" disabled={pending} onClick={() => setManualLevels(previous => new Set(previous).add(skill.skill_id))}>{t(skill.level_assessment ? 'Correct this estimate' : 'Set a level yourself')}</button></>}</div></div></details>}
          </div><button className="text-button skill-remove" disabled={pending} data-remove-skill={isRemoved ? undefined : index} data-restore-skill={isRemoved ? index : undefined} aria-label={t(`${isRemoved ? 'Restore' : 'Remove'} ${skill.label}`)} onClick={() => onRemove(skill.skill_id)}>{t(isRemoved ? 'Restore' : 'Remove')}</button>
        </div>;
      })}</div></div>) : <EmptyState title={t("A fresh starting point")} compact symbol="skills">{t("No recognized skills were found. Search below to add the skills you want to share.")}</EmptyState>}</div>
      <div className="add-skill surface"><label htmlFor="skill-search">{t("Add a skill")}</label><Search<Skill> id="skill-search" endpoint="/skills" resultKey="skills" placeholder={t("Search skills, tools or technologies")} disabled={pending} onSelect={onAdd} onError={onError} /></div>
      <div className="assessment-note caption" role="status">{profile.warnings.filter(text => text.startsWith("AI ")).map((text, index) => <p key={index}>{t(text)}</p>)}</div><Disclosure title={t("About extracted skills")} help><p>{t("Missing evidence doesn't mean you lack a skill. Confirmation is your own review, not an independent certification.")}</p><div id="profile-warnings">{t(profile.warnings.join(' '))}</div></Disclosure>
    </div><section className="preferences surface" aria-label={t("Career goal and learning preferences")} hidden={step !== 'direction'}><span className="mini-label">{t("MAKE IT PERSONAL")}</span><h2>{t("Your career goal")}</h2><label htmlFor="target-search">{t("Career goal ")}<span className="optional">{t("Optional")}</span></label>
      <Search<RoleSummary> id="target-search" endpoint="/roles" resultKey="roles" placeholder={t(target ? 'Search to change your occupation' : 'Search an occupation')} disabled={pending} onSelect={onTarget} onError={onError} />
      <div className={`target-selection ${target ? 'has-target' : ''}`} role="status" aria-live="polite" aria-atomic="true">
        {target ? <><span className="target-check"><Icon name="check" /></span><div className="target-copy"><span className="target-label">{t("Selected career goal")}</span><p id="selected-target">{t(target.role_title)}</p><span className="target-family">{t(target.family)}</span></div><button id="clear-target" className="text-button" disabled={pending} aria-label={t(`Clear career goal: ${target.role_title}`)} onClick={() => onTarget(null)}>{t("Clear")}</button></> : <p id="selected-target">{t("No career goal selected. You can still explore careers.")}</p>}
      </div><p className="caption">{t("Your goal stays visible. Its match score stays honest.")}</p>
      <Disclosure id="learning-preferences" title={t("Learning preferences")}><label htmlFor="budget">{t("Budget (MYR)")}</label><input id="budget" type="number" min="0" step="1" placeholder={t("Free resources only")} disabled={pending} value={preferences.budget} onChange={event => onPreferences({ ...preferences, budget: event.target.value })} /><label htmlFor="weekly-hours">{t("Hours per week")}</label><input id="weekly-hours" type="number" min="0.5" max="168" step="0.5" placeholder={t("e.g. 5")} disabled={pending} value={preferences.hours} onChange={event => onPreferences({ ...preferences, hours: event.target.value })} /><label htmlFor="interests">{t("Career interests")}</label><input id="interests" type="text" maxLength={200} placeholder={t("e.g. analytics, business")} disabled={pending} value={preferences.interests} onChange={event => onPreferences({ ...preferences, interests: event.target.value })} /><p className="caption">{t("Separate interests with commas.")}</p></Disclosure>
    </section></div>
    <div className={`continue-bar review-continue ${step === 'direction' ? 'direction-continue' : ''}`}>
      {step === 'skills' ? <><span id="review-progress">{t(`${confirmed} ${confirmed === 1 ? 'skill' : 'skills'} confirmed.`)}</span><button id="review-next" className="button primary" disabled={pending} onClick={() => setStep('direction')}>{t("Next: your direction ")}<Icon name="arrow" /></button></> : <><button id="back-to-skills" className="text-button" disabled={pending} onClick={() => setStep('skills')}>{t("← Back to skills")}</button><button id="find-matches" className="button primary" disabled={pending} onClick={onContinue}>{t(target ? 'Explore my careers' : 'Explore without a goal')} <Icon name="arrow" /></button></>}
    </div>
  </section>;
}
