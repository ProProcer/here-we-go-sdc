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

  return <Disclosure help title="Plan details & limitations">
    <div id="plan-facts">
      <p id="course-catalog-status">{courseStatus
        ? courseStatus.status === 'empty'
          ? 'The verified course catalog is currently empty. Learning objectives are available; course links, prices and durations are not.'
          : `${courseStatus.verified_course_count} verified courses in the catalog. Updated ${date(courseStatus.updated_at)}.`
        : 'Course catalog status is temporarily unavailable. Any verified resources in this plan remain listed above.'}</p>
      <dl className="plan-estimates">
        <div><dt>Verified course cost</dt><dd>{cost}</dd></div>
        <div><dt>Estimated course hours</dt><dd>{hours ?? 'Unavailable'}</dd></div>
        {weekly && hours ? <div><dt>Estimated pace</dt><dd>{Math.ceil(hours / weekly)} weeks at {weekly} hours/week</dd></div> : null}
      </dl>
    </div>
    <ul className="plan-notes">
      <li>CV extraction can miss context. Review your skills; missing evidence does not mean you lack a skill.</li>
      <li>Matches show skill coverage, not hiring chances. Education, licences and experience are not assessed.</li>
      <li>Learning priorities are guidance. Scenarios change priorities, not your skills or match score.</li>
      <li>{profile.constraints.budget_myr == null
        ? 'No budget set: only verified free-access courses are eligible.'
        : `Course budget: MYR ${profile.constraints.budget_myr.toFixed(2)}. Paid courses in other currencies are excluded.`}</li>
      {cacheOnly && <li>Course discovery currently uses the verified catalog only; live search is not connected.</li>}
    </ul>
    {warnings.length > 0 && <Disclosure title="Technical details" className="plan-technical">
      <p className="caption">Full backend notes for this plan. Also included in the JSON export.</p>
      <ul id="plan-warnings">{warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
    </Disclosure>}
  </Disclosure>;
}
