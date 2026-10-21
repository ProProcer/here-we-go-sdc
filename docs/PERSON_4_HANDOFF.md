# Person 4 handoff: learning planner and SDG engine

This handoff implements the internal Python subsystem that converts Person 2's
reviewed role gaps and Person 3's scenario priorities into a prerequisite-aware
learning plan. It also validates course candidates, maintains a JSON catalog,
and attaches curated UN SDG target explanations.

The subsystem is called directly by the containing application. It does not
start an HTTP server and does not require an API boundary between the frontend
and planner.

## Current status

Implemented:

- Typed contracts for verified courses, validation logs, prioritized gaps,
  learning steps, milestones, costs, SDG connections and `LearningPlan`.
- Direct integration with `src.intelligence.outlook.get_outlook()`.
- Trusted-provider-first discovery with wider-web fallback through an injected
  search provider.
- Bounded page validation with safe failure and audit logs.
- Prerequisite resolution, cycle rejection, weighted set-cover selection and
  duplicate-coverage pruning.
- Curated SDG 4.4 and cautious role-specific SDG 8.2 mappings.
- A JSON course/provider catalog and deterministic offline regression tests.

The committed course catalog contains trusted-provider configuration but no
course records. This is deliberate: a course enters `courses` only after it has
passed validation. With no cached course and no injected search provider, the
planner returns explicit `verified_resource_not_found` learning objectives
instead of inventing a provider, price or URL.

## Integration contract

Use Person 2's complete reviewed `SkillsProfile` and the user-selected
`RoleMatch`. Do not construct a new gap list from outlook data. The actual gaps
are `role_match.missing_skills`.

```python
from src.reskilling.planner import build_learning_plan

result = build_learning_plan(
    profile,
    selected_role_match,
    scenario_id,
    country="Malaysia",
    preferred_language="English",
    search_provider=course_search_provider,  # optional replaceable adapter
)

learning_plan = result.plan
validation_logs = result.validation_logs
```

### Required inputs

- `profile: SkillsProfile`: the complete reviewed Person 2 profile.
- `role_match: RoleMatch`: the selected result returned by Person 2.
- `scenario_id`: `baseline`, `moderate_ai_change` or `rapid_ai_change`.
- `country`: used for non-online availability.
- `preferred_language`: a ranking preference, including for online courses.

### Preserved Person 2 values

The planner revalidates and returns the reviewed skills and `fit_score` without
changing them. It rejects a stale match if a skill is simultaneously confirmed
in the profile and listed as missing in the supplied `RoleMatch`.

### Person 3 priority contract

The planner calls:

```python
get_outlook(role_match.role_id, scenario_id)
```

It joins `role_match.missing_skills` to
`outlook.scenario.skill_priorities` using `skill_id`. It consumes
`adjusted_priority` directly and preserves `baseline_priority` and
`applied_adjustment`. It does not multiply priorities or apply the adjustment a
second time. Outlook priorities establish importance only; they do not create a
gap or establish proficiency.

If a gap unexpectedly lacks an outlook priority, its Person 2 importance is
retained without adjustment and a warning is emitted.

### Output

`PlanningResult` contains:

- `plan: LearningPlan`
- `validation_logs: list[CourseValidationLog]`

`LearningPlan` contains the selected courses, ordered milestones, uncovered
skills, estimated hours, separate totals per currency, prioritized gaps, SDG
connections, reviewed skills, fit score and warnings.

## Course discovery

`CourseSearchProvider` is a replaceable protocol. The integration owner supplies
an adapter for the selected search service. It receives a `CourseSearchRequest`
containing the role, sector, skill, country, preferred language, requested source
tier and result limit, then returns `CourseCandidate` objects.

For each missing skill, the planner:

1. Reads eligible verified records from the JSON cache.
2. Requests trusted-provider candidates first.
3. Validates no more than 20 candidates in a batch.
4. Requests wider-web candidates when fewer than the configured target remain.
5. Adds only validated records to the in-memory catalog.
6. Atomically persists newly validated records when the existing cache is valid.

The default target is 20 valid candidates per skill. The planner also caps
prerequisite discovery at 20 unique skills. Both limits are configurable within
their validated bounds.

Trusted providers are configured by field/sector in
`data/processed/courses.json`. General providers are always included. Online
courses ignore country restrictions, while hybrid and in-person resources must
list matching availability. Language is preferred rather than used as an
absolute online-course exclusion.

## Course validation gates

A candidate is recommended only when all required checks pass:

- Safe public HTTPS URL and bounded HTML response.
- Redirect remains on the declared provider domain.
- Course title matches page or structured course evidence.
- Each claimed canonical skill has visible supporting page text.
- Enrollment or access is currently visible.
- Cost and currency are confirmed; missing price never becomes free.
- Duration is provider-stated or clearly identified as an estimate.
- Prerequisites have explicit page evidence.
- Language is supplied or inferred from page markup.
- Non-online location availability is known.

Validation outcomes are:

- `verified`: eligible for recommendation and caching.
- `withheld`: the page may exist, but required facts are uncertain.
- `rejected`: broken, unsafe, unrelated or provider-mismatched.

The default transport rejects local/private hosts, credentials, fragments,
non-HTML responses, oversized responses and requests exceeding the time budget.
The fetcher is injectable so tests do not require live internet access.

## Planning behavior

Course selection uses a deterministic weighted set-cover heuristic:

1. Sort actual gaps using `adjusted_priority`.
2. Resolve missing prerequisite skills recursively.
3. Reject unresolved or circular prerequisite chains.
4. Prefer newly covered priority weight and multi-skill coverage.
5. Use smaller course sets, preferred language, trusted source, lower stated
   cost and lower time burden as tie-breakers.
6. Remove redundant courses when coverage and prerequisite feasibility remain
   intact.
7. Topologically order prerequisites before dependent courses.

Costs in different currencies are never combined into one number. Paid totals
are returned separately by currency. Free access is distinguished from paid
access and free-to-audit access. The frontend may display or filter course cost
and duration, but removing a selected course can invalidate coverage or
prerequisites; any such change should trigger replanning against the remaining
eligible catalog rather than deleting a roadmap step in place.

Milestones currently use the agreed standard stages:

- `foundations`
- `core_skills`

Empty stages are omitted. Every verified course step includes a learning goal,
estimated hours, prerequisite skills, practice activity and suggested completion
evidence. An uncovered gap receives an explicit self-study objective with
`verified_resource_not_found`.

## SDG behavior

SDG mappings are loaded from `data/processed/sdg_mappings.json`. Rules must:

- Reference known canonical role and skill IDs.
- Use matching SDG and target numbers.
- Cite an official UN HTTPS page.
- State whether the connection is direct or indirect.

Current mappings cover:

- SDG 4, Target 4.4 for technical and vocational skill development.
- SDG 8, Target 8.2 as a cautious indirect connection for the three current
  role fixtures.

The rationales do not claim that courses guarantee employment, create jobs or
produce measured economy-wide productivity changes. Unsupported mappings are
omitted.

## Files

- `src/schemas/roadmap.py`: shared Pydantic contracts.
- `src/reskilling/course_catalog.py`: JSON catalog, provider groups and queries.
- `src/reskilling/validator.py`: bounded page transport and validation gates.
- `src/reskilling/planner.py`: priorities, discovery, prerequisites, selection and
  milestones.
- `src/reskilling/sdg_mapper.py`: curated rule loading and mapping.
- `data/processed/courses.json`: trusted provider configuration and verified
  course cache.
- `data/processed/sdg_mappings.json`: curated official-target rules.
- `tests/test_reskilling.py`: deterministic regression suite.

## Tests

The Person 4 suite contains 17 passing tests covering:

- Valid, nonexistent, broken, unrelated and unknown-price courses.
- Candidate limits and trusted-to-wider-web fallback.
- Provider configuration and cache preservation.
- Scenario response without double adjustment.
- Preservation of reviewed skills and fit score.
- Multi-skill set cover and duplicate coverage.
- Prerequisite ordering and circular prerequisites.
- Cost totals, milestones and uncovered-resource fallback.
- Official SDG evidence, unsupported mappings and invalid claims.

The full repository test run reaches 126 tests in the current checkout. All 17
Person 4 tests pass. One existing CV test cannot import in the inspection
environment because `pypdf` is not installed there; `pypdf` is already declared
in `requirements.txt`.

## Integration owner responsibilities

Person 5 or the containing application must:

1. Supply the reviewed `SkillsProfile` and selected `RoleMatch` from Person 2.
2. Pass the active scenario ID selected in the UI.
3. Supply country and preferred language.
4. Connect a concrete `CourseSearchProvider` when live discovery is desired.
5. Display warnings, uncovered skills and validation status without converting
   unknown facts into positive claims.
6. Keep scenario assumptions visibly hypothetical.

No separate HTTP API is required for this module. An API wrapper may still be
added later if the deployment architecture needs one.

## Known limitations

- The committed catalog has no pre-approved course records; without a search
  adapter, plans safely return uncovered learning objectives.
- Generic HTML validation may withhold JavaScript-only provider pages. A
  provider-specific adapter can be added without changing planner contracts.
- The current scenario fixture contains non-baseline assumptions for Data
  Analyst only. Other roles support baseline until matching scenario records are
  added by Person 3.
- Person 2 currently confirms skill presence, not required proficiency level, so
  the planner must not claim to measure mastery.
- Budget and time controls remain frontend concerns by team decision. They are
  returned as metadata and tie-breakers, not accepted as planner constraints.
- Role requirements, current profiles and current role catalog fixtures remain
  synthetic and must stay visibly labeled in the judged demo.
