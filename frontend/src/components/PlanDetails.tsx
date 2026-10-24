import { t } from '../i18n';
import type { CourseStatus, Plan, Profile } from '../types';
import { date, Disclosure } from './ui';

export default function PlanDetails({ plan, courseStatus, profile }: {
  plan: Plan; courseStatus: CourseStatus | null; profile: Profile;
}) {
  const hasCourses = plan.selected_courses.length > 0;
  const cost = plan.cost_totals.length
    ? plan.cost_totals.map(total => `${total.currency} ${total.amount.toFixed(2)}`).join(' + ')
    : hasCourses ? 'Verified free access' : 'Unavailable';
  const hours = plan.total_estimated_hours;
  const weekly = profile.constraints.hours_per_week;
  const warnings = [...new Set(plan.warnings)];
  const cacheOnly = warnings.some(warning => warning.includes('No search provider configured'));

  return <Disclosure help title={t("Plan details & limitations")}>
    <div id="plan-facts">
      <p id="course-catalog-status">{t(courseStatus
        ? courseStatus.status === 'empty'
          ? 'The verified course catalog is currently empty. Learning objectives are available; course links, prices and durations are not.'
          : `${courseStatus.verified_course_count} verified courses in the catalog. Updated ${date(courseStatus.updated_at)}.`
        : 'Course catalog status is temporarily unavailable. Any verified resources in this plan remain listed above.')}</p>
      <dl className="plan-estimates">
        <div><dt>{t("Verified course cost")}</dt><dd>{t(cost)}</dd></div>
        <div><dt>{t("Estimated course hours")}</dt><dd>{t(hours ?? 'Unavailable')}</dd></div>
        {weekly && hours ? <div><dt>{t("Estimated pace")}</dt><dd>{t(Math.ceil(hours / weekly))}{t(" weeks at ")}{t(weekly)}{t(" hours/week")}</dd></div> : null}
      </dl>
    </div>
    <ul className="plan-notes">
      <li>{t("CV extraction can miss context. Review your skills; missing evidence does not mean you lack a skill.")}</li>
      <li>{t("Matches show skill coverage, not hiring chances. Education, licences and experience are not assessed.")}</li>
      <li>{t("Learning priorities are guidance. Scenarios change priorities, not your skills or match score.")}</li>
      <li>{t(profile.constraints.budget_myr == null
        ? 'No budget set: only verified free-access courses are eligible.'
        : `Course budget: MYR ${profile.constraints.budget_myr.toFixed(2)}. Paid courses in other currencies are excluded.`)}</li>
      {cacheOnly && <li>{t("Course discovery currently uses the verified catalog only; live search is not connected.")}</li>}
    </ul>
    {warnings.length > 0 && <Disclosure title={t("Technical details")} className="plan-technical">
      <p className="caption">{t("Full backend notes for this plan. Also included in the JSON export.")}</p>
      <ul id="plan-warnings">{warnings.map(warning => <li key={warning}>{t(warning)}</li>)}</ul>
    </Disclosure>}
  </Disclosure>;
}
