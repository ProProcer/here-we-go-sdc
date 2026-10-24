import { t } from '../i18n';
import RoleScoreDetails from '../components/RoleScoreDetails';
import { Chip, Disclosure, ExternalLink, Icon, percent } from '../components/ui';
import { matchingSkills } from './Careers';
import type { Profile, RoleData } from '../types';

export default function RoleDetails({ data, profile, pending, selectedSoftware, hasPlan, onBack, onOutlook, onSoftware, onBuild, onReview }: {
  data: RoleData; profile: Profile; pending: boolean; selectedSoftware: Set<string>; hasPlan: boolean;
  onBack: () => void; onOutlook: () => void; onSoftware: (id: string, checked: boolean) => void;
  onBuild: () => void; onReview: () => void;
}) {
  const { match: role } = data;
  const skills = matchingSkills(role, profile);
  const breakdown = role.score_breakdown;
  const description = data.detail.role.description;
  const renderGap = (skill: typeof role.missing_skills[number]) => <li key={skill.skill_id}>
    <span>{t(skill.label)}</span><small>{t("Role importance ")}{skill.importance.toFixed(2)}</small>
  </li>;

  return <section id="role" className="screen career-detail-page">
    <button id="back-to-careers" className="button secondary back-link" disabled={pending} onClick={onBack}>{t("← Back to career matches")}</button>

    <header className="role-page-heading">
      <div><span className="eyebrow">{t(role.family)}</span><h1>{t(role.role_title)}</h1><p className="page-intro">{t("A closer look at your match and what to learn next.")}</p></div>
      <div id="role-fit" className="role-fit-badge"><strong>{role.fit_score.toFixed(2)}</strong><span>{t("personal fit / 100")}</span><small>{t("Match #")}{role.rank}</small></div>
    </header>

    <section className="surface role-overview" aria-labelledby="role-overview-heading">
      <span className="mini-label">{t("THE ROLE AT A GLANCE")}</span><h2 id="role-overview-heading">{t("Full occupation description")}</h2>
      <p id="role-description">{t(description)}</p>
    </section>

    <div className="role-skill-grid">
      <section className="surface role-skill-card" aria-labelledby="matched-heading">
        <div className="section-heading"><h2 id="matched-heading"><Icon name="check" />{t(" Matching skills")}</h2><span className="count-pill">{skills.length}</span></div>
        <p className="caption">{t("Confirmed skills connected to this career.")}</p>
        <div id="matched-skills" className="skill-scroll-window" role="region" aria-labelledby="matched-heading" tabIndex={0}>{skills.length ? skills.map(skill => <details className="role-skill-evidence" key={skill.skill_id}><summary><span>{t(skill.label)}<small>{t("View CV evidence")}</small></span><Icon name="chevron" /></summary><ul>{skill.evidence.map((text, index) => <li key={index}>{t(text)}</li>)}</ul></details>) : <p>{t("No confirmed requirements yet.")}</p>}</div>
      </section>
      <section className="surface role-skill-card" aria-labelledby="gap-heading">
        <div className="section-heading"><h2 id="gap-heading"><Icon name="path" />{t(" Skills to explore")}</h2><span className="count-pill">{role.missing_skills.length}</span></div>
        <p className="caption">{t("Not yet confirmed in your profile. You may already have them.")}</p>
        <div id="skills-to-explore" className="skill-scroll-window" role="region" aria-labelledby="gap-heading" tabIndex={0}>
          <ul id="gap-list" className="role-gap-preview">{t(role.missing_skills.map(renderGap))}</ul>
          {!role.missing_skills.length && <p>{t("All general skill requirements are covered.")}</p>}
          <Disclosure help title={t("What role importance means")}><p>{t("Importance is the occupation’s O*NET rating divided by 5. A value of 0.80 means 4 out of 5 for this role. It does not measure your proficiency or a skill deficit.")}</p></Disclosure>
        </div>
        {role.missing_skills.length > 0 && <button className="button secondary skill-review-button" disabled={pending} onClick={onReview}>{t("Review my skills ")}<Icon name="arrow" /></button>}
      </section>
    </div>

    <section className="surface role-match-summary" aria-labelledby="match-heading">
      <div className="section-heading"><h2 id="match-heading">{t("Why this match?")}</h2><Chip>{t("Based on your skills")}</Chip></div>
      <div className="role-score-grid">{([
        ['CV skill alignment', breakdown.profile_alignment],
        ['General requirement fulfilment', breakdown.general_fulfilment],
      ] as const).map(([label, value]) => <div className="role-score" key={label}><div><span>{t(label)}</span><strong>{t(percent(value))}</strong></div><meter min={0} max={1} value={value} aria-label={t(label)} /></div>)}</div>
      <p className="caption">{t("An exploratory fit score, not a hiring probability.")}</p>
      <Disclosure title={t("See score breakdown & proficiency")}><RoleScoreDetails role={role} /></Disclosure>
    </section>

    <section className="surface role-tools" aria-labelledby="tools-heading">
      <div className="section-heading"><h2 id="tools-heading">{t("Tools you could learn")}</h2><Chip>{t("Optional")}</Chip></div>
      <p className="caption">{t("Pick tools to include in your roadmap.")}</p>
      <Disclosure title={t(`Choose software${selectedSoftware.size ? ` · ${selectedSoftware.size} selected` : ''}`)}><div id="software-options" className="software-options">{role.software_learning_options.length ? role.software_learning_options.map((skill, index) => <label className="software-choice" key={skill.skill_id}><input type="checkbox" value={skill.skill_id} id={`software-${index}`} disabled={pending} checked={selectedSoftware.has(skill.skill_id)} onChange={event => onSoftware(skill.skill_id, event.target.checked)} /><span>{t(skill.label)}{skill.group_familiarity_evidenced && <small>{t("Related category familiarity is present.")}</small>}</span></label>) : <p>{t("No unmatched in-demand software options for this role.")}</p>}</div></Disclosure>
    </section>

    <section className="role-next-page" aria-labelledby="outlook-next-heading">
      <span className="role-next-icon"><Icon name="spark" /></span><div><span className="mini-label">{t("UP NEXT")}</span><h2 id="outlook-next-heading">{t("How could AI change this career?")}</h2><p>{t("Explore research findings and practical skills to build.")}</p></div>
      <button id="open-ai-outlook" className="button primary" disabled={pending} onClick={onOutlook}>{t("AI outlook ")}<Icon name="arrow" /></button>
    </section>

    <div className="role-extra-details">
      {Boolean(data.detail.sdg_connections?.length) && <Disclosure title={t("This career’s SDG contribution")}><div id="role-sdg-connections">{data.detail.sdg_connections?.map((connection, index) => <div className="sdg-connection" key={index}><Chip>{t(connection.sdg_id)}{t(" · Target ")}{t(connection.target_id)}</Chip><p className="caption">{t(connection.scope === 'career_preparation' ? 'Career preparation' : 'Conditional work application')}</p><p>{t(connection.rationale)}</p><ExternalLink button url={connection.evidence_url}>{t("Read the official UN target")}</ExternalLink></div>)}</div><p className="caption">{t("Possible contributions, not measured SDG outcomes.")}</p></Disclosure>}
      <Disclosure help title={t("Score & data limitations")}><ul id="match-warnings">{role.warnings.map((warning, index) => <li key={index}>{t(warning)}</li>)}<li>{t("Skills score weight: ")}{t(percent(breakdown.readiness_weight))}{t(". Preference weight: ")}{t(percent(breakdown.preference_weight))}.</li><li>{t("Category familiarity does not establish proficiency in another tool.")}</li><li>{t("O*NET describes U.S. occupations and does not establish Malaysian vacancies or hiring eligibility.")}</li></ul></Disclosure>
    </div>
    <div className="role-page-footer"><span className="caption">{t("Ready to start learning?")}</span><button id="build-roadmap" className="button secondary" disabled={pending} onClick={onBuild}>{t(hasPlan ? 'Return to my roadmap' : 'Build my roadmap')} <Icon name="arrow" /></button></div>
  </section>;
}
