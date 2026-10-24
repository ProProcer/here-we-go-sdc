import { t } from '../i18n';
import { courseSources } from '../courseSources';
import { ExternalLink } from './ui';

export default function CourseSources({ skills, hasCourse }: { skills: string[]; hasCourse: boolean }) {
  return <section className="course-source-options" aria-label={t("Other learning providers")}>
    <h4>{t(hasCourse ? 'Explore other providers' : 'Find a learning resource')}</h4>
    <p className="caption">{t("Optional choices. Check access, fees and entry requirements with the provider.")}</p>
    <div className="course-source-list">{courseSources(skills).map(source => <div className="course-source-option" key={source.url}>
      <div><strong>{t(source.title)}</strong><small>{t(source.provider)} · {t(source.catalog ? 'Course catalog' : 'Course')}</small></div>
      <ExternalLink button url={source.url}>{t(source.catalog ? 'Browse' : 'View course')}</ExternalLink>
    </div>)}</div>
  </section>;
}
