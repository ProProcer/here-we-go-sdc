"""Personalized, scenario-aware learning-plan orchestration."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from typing import Literal, Protocol

from pydantic import Field

from src.ingestion.catalog import load_role_catalog
from src.ingestion.selection import Catalog
from src.intelligence.outlook import RoleOutlook, get_outlook
from src.reskilling.course_catalog import (
    DEFAULT_COURSE_CATALOG,
    CourseCatalog,
    CourseCatalogError,
    CourseCatalogStore,
    courses_for_skills,
    trusted_providers_for_family,
)
from src.reskilling.sdg_mapper import SDGRuleSet, map_sdg_connections
from src.reskilling.validator import (
    CourseCandidate,
    PageFetcher,
    fetch_course_page,
    validate_course_candidates,
)
from src.schemas.onet import OnetCatalog
from src.schemas.onet_profile import OnetRoleMatch
from src.schemas.onet_roadmap import OnetLearningPlan
from src.schemas.profile import RoleMatch, SkillContribution, SkillsProfile
from src.schemas.roadmap import (
    CostTotal,
    CourseValidationLog,
    LearningPlan,
    LearningStep,
    Milestone,
    PrioritizedGap,
    VerifiedCourse,
)
from src.schemas.role import Contract

OutlookLoader = Callable[[str, str], RoleOutlook]


@dataclass(frozen=True)
class CourseSearchRequest:
    role_id: str
    role_title: str
    sector_id: str | None
    skill_id: str
    skill_label: str
    country: str
    preferred_language: str
    source_tier: Literal["trusted", "wider_web"]
    limit: int
    family_id: str | None = None
    provider_domains: tuple[str, ...] = ()


class CourseSearchProvider(Protocol):
    def search(self, request: CourseSearchRequest) -> Iterable[CourseCandidate]: ...


class CourseSearchUnavailable(RuntimeError):
    """Expected failure raised by a replaceable course-search provider."""


class PlanningResult(Contract):
    plan: OnetLearningPlan | LearningPlan
    validation_logs: list[CourseValidationLog] = Field(default_factory=list)


def _prioritize_gaps(
    role_match: RoleMatch | OnetRoleMatch, outlook: RoleOutlook
) -> tuple[list[PrioritizedGap], list[str]]:
    priorities = {
        priority.skill_id: priority for priority in outlook.scenario.skill_priorities
    }
    gaps = []
    warnings = []
    for gap in role_match.missing_skills:
        priority = priorities.get(gap.skill_id)
        if priority is None:
            warnings.append(
                f"No scenario priority was available for {gap.skill_id}; "
                "Person 2 importance was retained without adjustment."
            )
            baseline = adjusted = gap.importance
            adjustment = 0.0
        else:
            baseline = priority.baseline_priority
            adjusted = priority.adjusted_priority
            adjustment = priority.applied_adjustment
        gaps.append(
            PrioritizedGap(
                skill_id=gap.skill_id,
                label=gap.label,
                gap_reason=gap.reason,
                person2_importance=gap.importance,
                baseline_priority=baseline,
                applied_adjustment=adjustment,
                adjusted_priority=adjusted,
            )
        )
    gaps.sort(key=lambda gap: (-gap.adjusted_priority, gap.skill_id))
    return gaps, warnings


def _catalog_view(courses: dict[str, VerifiedCourse]) -> CourseCatalog:
    return CourseCatalog(
        courses=sorted(courses.values(), key=lambda item: item.course_id)
    )


def _eligible_for_skill(
    courses: dict[str, VerifiedCourse],
    skill_id: str,
    *,
    country: str,
    preferred_language: str,
) -> list[VerifiedCourse]:
    return courses_for_skills(
        _catalog_view(courses),
        [skill_id],
        country=country,
        preferred_language=preferred_language,
    )


def _discover_for_skill(
    *,
    skill_id: str,
    skill_label: str,
    role_match: RoleMatch | OnetRoleMatch,
    country: str,
    preferred_language: str,
    target_candidates: int,
    courses: dict[str, VerifiedCourse],
    search_provider: CourseSearchProvider | None,
    fetcher: PageFetcher,
    catalog: Catalog,
    logs: list[CourseValidationLog],
    warnings: list[str],
    provider_catalog: CourseCatalog | None = None,
) -> None:
    """Search trusted sources first, then wider sources if coverage stays thin."""

    if search_provider is None:
        if (
            len(
                _eligible_for_skill(
                    courses,
                    skill_id,
                    country=country,
                    preferred_language=preferred_language,
                )
            )
            < target_candidates
        ):
            warnings.append(
                f"No search provider configured for {skill_id}; using verified cache only."
            )
        return

    seen_urls = {str(course.course_url) for course in courses.values()}

    def search_tier(tier: Literal["trusted", "wider_web"], limit: int) -> None:
        if limit <= 0:
            return
        request = CourseSearchRequest(
            role_id=role_match.role_id,
            role_title=role_match.role_title,
            sector_id=role_match.sector_id
            if isinstance(role_match, RoleMatch)
            else None,
            skill_id=skill_id,
            skill_label=skill_label,
            country=country,
            preferred_language=preferred_language,
            source_tier=tier,
            limit=limit,
            family_id=role_match.family_id
            if isinstance(role_match, OnetRoleMatch)
            else None,
            provider_domains=tuple(
                domain
                for provider in trusted_providers_for_family(
                    provider_catalog or CourseCatalog(), role_match.family_id
                )
                for domain in provider.domains
            )
            if isinstance(role_match, OnetRoleMatch) and tier == "trusted"
            else (),
        )
        try:
            raw = list(islice(search_provider.search(request), limit))
        except CourseSearchUnavailable as exc:
            warnings.append(f"Course search unavailable for {skill_id}: {exc}")
            return

        candidates = []
        for candidate in raw:
            url = str(candidate.course_url)
            if candidate.source_tier != tier:
                warnings.append(
                    f"Search provider returned a mismatched source tier for {url}."
                )
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(candidate)

        outcomes = validate_course_candidates(
            candidates,
            max_candidates=limit,
            fetcher=fetcher,
            catalog=catalog,
        )
        for outcome in outcomes:
            logs.append(outcome.log)
            if outcome.course is not None:
                courses[outcome.course.course_id] = outcome.course

    eligible = _eligible_for_skill(
        courses,
        skill_id,
        country=country,
        preferred_language=preferred_language,
    )
    trusted_count = sum(course.source_tier == "trusted" for course in eligible)
    search_tier("trusted", target_candidates - trusted_count)

    eligible = _eligible_for_skill(
        courses,
        skill_id,
        country=country,
        preferred_language=preferred_language,
    )
    if len(eligible) < target_candidates:
        search_tier("wider_web", target_candidates - len(eligible))


def _course_preference_key(
    course: VerifiedCourse, skill_id: str, preferred_language: str
) -> tuple:
    return (
        -course.coverage_strength.get(skill_id, 0),
        -int(course.language.casefold() == preferred_language.casefold()),
        -int(course.source_tier == "trusted"),
        int(course.cost.amount > 0),
        course.duration.hours,
        course.course_id,
    )


def _resolve_course_closure(
    course: VerifiedCourse,
    candidates: list[VerifiedCourse],
    known_skills: set[str],
    preferred_language: str,
    visiting: frozenset[str] = frozenset(),
) -> list[VerifiedCourse] | None:
    """Return prerequisite courses before the requested course, or None."""

    if course.course_id in visiting or len(visiting) >= 20:
        return None
    visiting = visiting | {course.course_id}
    resolved: list[VerifiedCourse] = []
    resolved_ids: set[str] = set()
    acquired = set(known_skills)

    for prerequisite in sorted(course.prerequisite_skill_ids):
        if prerequisite in acquired:
            continue
        options = sorted(
            (
                item
                for item in candidates
                if prerequisite in item.skill_ids and item.course_id != course.course_id
            ),
            key=lambda item: _course_preference_key(
                item, prerequisite, preferred_language
            ),
        )
        chosen = None
        for option in options:
            closure = _resolve_course_closure(
                option,
                candidates,
                acquired,
                preferred_language,
                visiting,
            )
            if closure is not None:
                chosen = closure
                break
        if chosen is None:
            return None
        for item in chosen:
            if item.course_id not in resolved_ids:
                resolved.append(item)
                resolved_ids.add(item.course_id)
                acquired.update(item.skill_ids)

    if course.course_id not in resolved_ids:
        resolved.append(course)
    return resolved


def _topological_courses(
    courses: list[VerifiedCourse], reviewed_skills: set[str]
) -> tuple[list[VerifiedCourse], set[str]] | None:
    by_id = {course.course_id: course for course in courses}
    order_index = {course.course_id: index for index, course in enumerate(courses)}
    edges: dict[str, set[str]] = {course.course_id: set() for course in courses}
    indegree = {course.course_id: 0 for course in courses}
    prerequisite_course_ids: set[str] = set()

    for dependent in courses:
        for prerequisite in dependent.prerequisite_skill_ids:
            if prerequisite in reviewed_skills:
                continue
            providers = sorted(
                (
                    course
                    for course in courses
                    if course.course_id != dependent.course_id
                    and prerequisite in course.skill_ids
                ),
                key=lambda course: (
                    order_index[course.course_id],
                    -course.coverage_strength.get(prerequisite, 0),
                ),
            )
            if not providers:
                return None
            provider = providers[0]
            if dependent.course_id not in edges[provider.course_id]:
                edges[provider.course_id].add(dependent.course_id)
                indegree[dependent.course_id] += 1
                prerequisite_course_ids.add(provider.course_id)

    ready = sorted(
        (course_id for course_id, degree in indegree.items() if degree == 0),
        key=order_index.get,
    )
    ordered = []
    while ready:
        course_id = ready.pop(0)
        ordered.append(by_id[course_id])
        for dependent_id in sorted(edges[course_id], key=order_index.get):
            indegree[dependent_id] -= 1
            if indegree[dependent_id] == 0:
                ready.append(dependent_id)
                ready.sort(key=order_index.get)
    if len(ordered) != len(courses):
        return None
    return ordered, prerequisite_course_ids


def _select_courses(
    gaps: list[PrioritizedGap],
    candidates: list[VerifiedCourse],
    reviewed_skills: set[str],
    preferred_language: str,
    budget_myr: float | None = None,
) -> tuple[list[VerifiedCourse], set[str], set[str]]:
    weights = {gap.skill_id: gap.adjusted_priority for gap in gaps}
    uncovered = set(weights)
    selected: list[VerifiedCourse] = []
    selected_ids: set[str] = set()

    while uncovered:
        known = reviewed_skills | {
            skill_id for course in selected for skill_id in course.skill_ids
        }
        ranked = []
        for course in candidates:
            if course.course_id in selected_ids:
                continue
            closure = _resolve_course_closure(
                course,
                candidates,
                known,
                preferred_language,
            )
            if closure is None:
                continue
            new_closure = [
                item for item in closure if item.course_id not in selected_ids
            ]
            if budget_myr is not None:
                proposed = [*selected, *new_closure]
                if any(
                    c.cost.amount > 0 and c.cost.currency != "MYR" for c in proposed
                ):
                    continue
                if sum(c.cost.amount for c in proposed) > budget_myr:
                    continue
            coverage = {
                skill_id: max(
                    (item.coverage_strength.get(skill_id, 0) for item in new_closure),
                    default=0,
                )
                for skill_id in uncovered
            }
            newly_covered = {
                skill_id for skill_id, strength in coverage.items() if strength > 0
            }
            if not newly_covered:
                continue
            weighted_coverage = sum(
                weights[skill_id] * coverage[skill_id] for skill_id in newly_covered
            )
            language_matches = sum(
                item.language.casefold() == preferred_language.casefold()
                for item in new_closure
            )
            trusted_count = sum(item.source_tier == "trusted" for item in new_closure)
            paid_count = sum(item.cost.amount > 0 for item in new_closure)
            stated_cost = sum(item.cost.amount for item in new_closure)
            hours = sum(item.duration.hours for item in new_closure)
            key = (
                -weighted_coverage,
                -len(newly_covered),
                len(new_closure),
                -language_matches,
                -trusted_count,
                paid_count,
                stated_cost,
                hours,
                course.course_id,
            )
            ranked.append((key, new_closure, newly_covered))

        if not ranked:
            break
        _, chosen, newly_covered = min(ranked, key=lambda item: item[0])
        for course in chosen:
            if course.course_id not in selected_ids:
                selected.append(course)
                selected_ids.add(course.course_id)
        uncovered -= newly_covered

    target_skills = set(weights)
    for course in list(reversed(selected)):
        current_coverage = {
            skill_id for item in selected for skill_id in item.skill_ids
        }
        trial = [item for item in selected if item.course_id != course.course_id]
        trial_coverage = {skill_id for item in trial for skill_id in item.skill_ids}
        required_coverage = target_skills & current_coverage
        if (
            required_coverage <= trial_coverage
            and _topological_courses(trial, reviewed_skills) is not None
        ):
            selected = trial

    ordered_result = _topological_courses(selected, reviewed_skills)
    if ordered_result is None:
        return [], set(weights), set()
    ordered, prerequisite_course_ids = ordered_result
    covered = {skill_id for course in ordered for skill_id in course.skill_ids}
    return ordered, set(weights) - covered, prerequisite_course_ids


def _build_milestones(
    *,
    courses: list[VerifiedCourse],
    gaps: list[PrioritizedGap],
    uncovered: set[str],
    prerequisite_course_ids: set[str],
    role_title: str,
) -> list[Milestone]:
    labels = {gap.skill_id: gap.label for gap in gaps}
    gap_ids = set(labels)
    first_core = next(
        (
            index
            for index, course in enumerate(courses)
            if set(course.skill_ids) & gap_ids
        ),
        len(courses),
    )
    foundation_courses = [
        course
        for course in courses[:first_core]
        if course.course_id in prerequisite_course_ids
    ]
    foundation_ids = {course.course_id for course in foundation_courses}
    core_courses = [
        course for course in courses if course.course_id not in foundation_ids
    ]
    order = 1

    def course_steps(items: list[VerifiedCourse]) -> list[LearningStep]:
        nonlocal order
        steps = []
        for course in items:
            names = [labels.get(skill_id, skill_id) for skill_id in course.skill_ids]
            summary = ", ".join(names)
            steps.append(
                LearningStep(
                    order=order,
                    skill_ids=course.skill_ids,
                    learning_goal=f"Build practical capability in {summary}.",
                    course_id=course.course_id,
                    estimated_hours=course.duration.hours,
                    prerequisite_skill_ids=course.prerequisite_skill_ids,
                    practice_activity=(
                        f"Complete an exercise applying {summary} to a "
                        f"{role_title} task."
                    ),
                    completion_evidence=(
                        "Save the completed exercise and available course "
                        "completion evidence."
                    ),
                    resource_status="verified",
                )
            )
            order += 1
        return steps

    milestones = []
    if foundation_courses:
        milestones.append(
            Milestone(
                stage="foundations",
                title="Foundations",
                objective="Complete prerequisites required by later learning.",
                steps=course_steps(foundation_courses),
            )
        )

    core_steps = course_steps(core_courses)
    for gap in gaps:
        if gap.skill_id not in uncovered:
            continue
        core_steps.append(
            LearningStep(
                order=order,
                skill_ids=[gap.skill_id],
                learning_goal=(
                    f"Develop {gap.label} through a documented self-study "
                    "objective while no verified course is available."
                ),
                prerequisite_skill_ids=[],
                practice_activity=(
                    f"Create a small {role_title} exercise demonstrating {gap.label}."
                ),
                completion_evidence="Save the exercise, notes, and review criteria.",
                resource_status="verified_resource_not_found",
            )
        )
        order += 1
    if core_steps:
        milestones.append(
            Milestone(
                stage="core_skills",
                title="Core Skills",
                objective="Address the selected role's prioritized skill gaps.",
                steps=core_steps,
            )
        )
    return milestones


def _cost_totals(courses: list[VerifiedCourse]) -> list[CostTotal]:
    totals: dict[str, float] = defaultdict(float)
    for course in courses:
        if course.cost.amount > 0 and course.cost.currency is not None:
            totals[course.cost.currency] += course.cost.amount
    return [
        CostTotal(currency=currency, amount=round(amount, 2))
        for currency, amount in sorted(totals.items())
    ]


def build_learning_plan(
    profile: SkillsProfile,
    role_match: RoleMatch | OnetRoleMatch,
    scenario_id: Literal["baseline", "moderate_ai_change", "rapid_ai_change"],
    *,
    country: str,
    preferred_language: str,
    course_store: CourseCatalogStore | None = None,
    search_provider: CourseSearchProvider | None = None,
    fetcher: PageFetcher = fetch_course_page,
    sdg_rules: SDGRuleSet | None = None,
    catalog: Catalog | None = None,
    outlook_loader: OutlookLoader | None = None,
    target_candidates_per_skill: int = 20,
    max_prerequisite_skills: int = 20,
    generated_at: datetime | None = None,
    selected_software_skill_ids: list[str] | None = None,
) -> PlanningResult:
    """Build one best-coverage plan without changing Person 2's fit result."""

    if (
        isinstance(target_candidates_per_skill, bool)
        or not isinstance(target_candidates_per_skill, int)
        or not 1 <= target_candidates_per_skill <= 20
    ):
        raise ValueError("target_candidates_per_skill must be an integer from 1 to 20")
    if (
        isinstance(max_prerequisite_skills, bool)
        or not isinstance(max_prerequisite_skills, int)
        or max_prerequisite_skills < 0
    ):
        raise ValueError("max_prerequisite_skills must be a non-negative integer")
    country = country.strip()
    preferred_language = preferred_language.strip()
    if not country or not preferred_language:
        raise ValueError("Country and preferred language are required")

    profile = SkillsProfile.model_validate(profile.model_dump())
    match_type = OnetRoleMatch if isinstance(role_match, OnetRoleMatch) else RoleMatch
    role_match = match_type.model_validate(role_match.model_dump())
    catalog = catalog if catalog is not None else load_role_catalog()
    is_onet = isinstance(catalog, OnetCatalog)
    if is_onet != isinstance(role_match, OnetRoleMatch):
        raise ValueError("Role match and catalog versions disagree")
    selected_software = sorted(set(selected_software_skill_ids or []))
    if not is_onet and selected_software:
        raise ValueError("Optional software selection requires the real catalog")
    budget_myr = None
    original_options = []
    if is_onet:
        from src.profiles.onet_matching import OnetMatcher

        expected = OnetMatcher(catalog).match_role(
            profile,
            role_match.role_id,
            policy=role_match.score_breakdown.coverage.policy,
        )
        if role_match.model_dump(exclude={"rank", "pinned"}) != expected.model_dump(
            exclude={"rank", "pinned"}
        ):
            raise ValueError(
                "Role match is stale or altered; recompute it from the reviewed profile"
            )
        original_options = role_match.software_learning_options
        options = {o.skill_id: o for o in original_options}
        if not set(selected_software) <= options.keys():
            raise ValueError(
                "Selected software must be an unmatched occupation-specific learning option"
            )
        extra = [
            SkillContribution(
                skill_id=sid,
                label=options[sid].label,
                importance=0.5,
                coverage=0,
                weighted_contribution=0,
                evidence=[],
                reason="User-selected optional software objective; 0.5 is application learning priority, not measured tool importance.",
            )
            for sid in selected_software
        ]
        role_match = role_match.model_copy(
            update={"missing_skills": [*role_match.missing_skills, *extra]}
        )
        budget_myr = (
            profile.constraints.budget_myr
            if profile.constraints.budget_myr is not None
            else 0.0
        )
    if role_match.role_id not in {role.role_id for role in catalog.roles}:
        raise ValueError(f"Unknown selected role: {role_match.role_id}")
    reviewed_skills = {
        skill.skill_id
        for skill in profile.skills
        if skill.confirmation in {"self_reported", "confirmed"}
    }
    stale_gaps = reviewed_skills & {gap.skill_id for gap in role_match.missing_skills}
    if stale_gaps:
        raise ValueError(
            "Role match is stale relative to the reviewed profile: "
            f"{sorted(stale_gaps)}"
        )

    outlook = (
        outlook_loader(role_match.role_id, scenario_id)
        if outlook_loader is not None
        else get_outlook(role_match.role_id, scenario_id, catalog=catalog)
    )
    if (
        outlook.role_id != role_match.role_id
        or outlook.catalog_synthetic != catalog.synthetic
    ):
        raise ValueError("Outlook and selected catalog/role disagree")
    gaps, priority_warnings = _prioritize_gaps(role_match, outlook)
    warnings = [*role_match.warnings, *priority_warnings]
    if is_onet:
        warnings.extend(
            [
                "Only explicitly selected optional software is included in the learning plan.",
                "Budget is enforced in MYR; foreign-currency paid routes are withheld rather than guessing exchange rates.",
            ]
        )
        if profile.constraints.budget_myr is None:
            warnings.append(
                "No budget supplied; only verified zero-cost access routes are eligible."
            )
    logs: list[CourseValidationLog] = []

    course_store = (
        course_store
        if course_store is not None
        else CourseCatalogStore(
            DEFAULT_COURSE_CATALOG.parent / "onet/31.0/courses.json"
            if is_onet
            else DEFAULT_COURSE_CATALOG
        )
    )
    cache_writable = True
    try:
        stored_catalog = course_store.load()
    except CourseCatalogError as exc:
        stored_catalog = CourseCatalog()
        cache_writable = False
        warnings.append(str(exc) + "; invalid cache was not overwritten.")
    courses = {course.course_id: course for course in stored_catalog.courses}
    original_course_ids = set(courses)

    labels = {skill.skill_id: skill.label for skill in catalog.taxonomy.skills}
    searched_skills: set[str] = set()
    for gap in gaps:
        _discover_for_skill(
            skill_id=gap.skill_id,
            skill_label=gap.label,
            role_match=role_match,
            country=country,
            preferred_language=preferred_language,
            target_candidates=target_candidates_per_skill,
            courses=courses,
            search_provider=search_provider,
            fetcher=fetcher,
            catalog=catalog,
            logs=logs,
            warnings=warnings,
            provider_catalog=stored_catalog,
        )
        searched_skills.add(gap.skill_id)

    prerequisite_count = 0
    while prerequisite_count < max_prerequisite_skills:
        relevant = [
            course
            for course in courses.values()
            if set(course.skill_ids) & searched_skills
        ]
        pending = sorted(
            {
                skill_id
                for course in relevant
                for skill_id in course.prerequisite_skill_ids
                if skill_id not in reviewed_skills
                and skill_id not in searched_skills
                and skill_id in labels
            }
        )
        if not pending:
            break
        for skill_id in pending:
            if prerequisite_count >= max_prerequisite_skills:
                warnings.append("Prerequisite discovery limit reached.")
                break
            _discover_for_skill(
                skill_id=skill_id,
                skill_label=labels[skill_id],
                role_match=role_match,
                country=country,
                preferred_language=preferred_language,
                target_candidates=target_candidates_per_skill,
                courses=courses,
                search_provider=search_provider,
                fetcher=fetcher,
                catalog=catalog,
                logs=logs,
                warnings=warnings,
                provider_catalog=stored_catalog,
            )
            searched_skills.add(skill_id)
            prerequisite_count += 1

    if cache_writable and set(courses) != original_course_ids:
        try:
            course_store.save(courses.values())
        except OSError:
            warnings.append(
                "Validated courses could not be persisted to the JSON cache."
            )

    candidates = courses_for_skills(
        _catalog_view(courses),
        searched_skills,
        country=country,
        preferred_language=preferred_language,
    )
    selected, uncovered, prerequisite_course_ids = _select_courses(
        gaps,
        candidates,
        reviewed_skills,
        preferred_language,
        budget_myr=budget_myr,
    )
    if uncovered:
        warnings.append(
            "Verified resources were not found for: " + ", ".join(sorted(uncovered))
        )

    milestones = _build_milestones(
        courses=selected,
        gaps=gaps,
        uncovered=uncovered,
        prerequisite_course_ids=prerequisite_course_ids,
        role_title=role_match.role_title,
    )
    planned_skill_ids = [gap.skill_id for gap in gaps]
    sdg_connections = map_sdg_connections(
        role_match.role_id,
        planned_skill_ids,
        rules=sdg_rules,
        catalog=catalog,
    )
    if planned_skill_ids and not sdg_connections:
        warnings.append("No curated SDG mapping was available for the planned skills.")
    if selected and all(course.cost.amount == 0 for course in selected):
        warnings.append("All selected access routes were verified at zero cost.")

    generated_at = generated_at or datetime.now(UTC)
    if generated_at.utcoffset() is None:
        raise ValueError("generated_at must include a UTC offset")
    plan_type = OnetLearningPlan if is_onet else LearningPlan
    extra_plan = (
        {
            "family_id": role_match.family_id,
            "family": role_match.family,
            "software_learning_options": original_options,
            "selected_software_skill_ids": selected_software,
            "budget_myr": budget_myr,
        }
        if is_onet
        else {}
    )
    plan = plan_type(
        **extra_plan,
        generated_at=generated_at,
        profile_id=profile.profile_id,
        role_id=role_match.role_id,
        scenario_id=scenario_id,
        fit_score=role_match.fit_score,
        reviewed_skills=profile.skills,
        prioritized_gaps=gaps,
        selected_courses=selected,
        milestones=milestones,
        uncovered_skill_ids=sorted(uncovered),
        total_estimated_hours=(
            sum(course.duration.hours for course in selected) if selected else None
        ),
        cost_totals=_cost_totals(selected),
        sdg_connections=sdg_connections,
        warnings=list(dict.fromkeys(warnings)),
    )
    return PlanningResult(plan=plan, validation_logs=logs)
