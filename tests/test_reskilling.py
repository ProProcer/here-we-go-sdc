"""Regression tests for course validation, planning, and SDG mapping."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from src.profiles.intake import create_profile
from src.profiles.matching import match_roles
from src.reskilling.course_catalog import (
    CourseCatalog,
    CourseCatalogError,
    CourseCatalogStore,
    trusted_providers_for_sector,
)
from src.reskilling.planner import CourseSearchRequest, build_learning_plan
from src.reskilling.sdg_mapper import (
    SDGRule,
    SDGRuleSet,
    load_sdg_rules,
    map_sdg_connections,
)
from src.reskilling.validator import (
    CourseCandidate,
    FetchedPage,
    validate_course_candidate,
    validate_course_candidates,
)
from src.schemas.roadmap import CourseCost, CourseDuration, VerifiedCourse


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def make_course(
    course_id,
    skills,
    *,
    prerequisites=(),
    hours=5,
    access="free",
    amount=0,
    currency=None,
    source_tier="trusted",
    language="English",
):
    slug = course_id.split(":", 1)[1]
    return VerifiedCourse(
        course_id=course_id,
        title=slug.replace("_", " ").title(),
        provider="Example University",
        course_url=f"https://example.com/{slug}",
        evidence_url=f"https://example.com/{slug}",
        source_tier=source_tier,
        skill_ids=list(skills),
        coverage_strength={skill_id: 1.0 for skill_id in skills},
        cost=CourseCost(
            access=access,
            amount=amount,
            currency=currency,
            includes_certificate=access == "paid",
        ),
        duration=CourseDuration(
            hours=hours,
            display_text=f"{hours} hours",
            basis="provider_stated",
        ),
        prerequisite_skill_ids=list(prerequisites),
        delivery_mode="online",
        language=language,
        last_verified_at=NOW,
    )


def make_candidate(
    skill_id="skill:sql",
    title="Practical SQL",
    *,
    source_tier="trusted",
    cost=True,
    url="https://example.com/practical-sql",
):
    return CourseCandidate(
        title=title,
        provider="Example University",
        course_url=url,
        provider_domains=["example.com"],
        source_tier=source_tier,
        skill_ids=[skill_id],
        coverage_strength={skill_id: 1.0},
        cost=(
            CourseCost(
                access="free",
                amount=0,
                includes_certificate=False,
            )
            if cost
            else None
        ),
        duration=CourseDuration(
            hours=5,
            display_text="5 hours",
            basis="provider_stated",
        ),
        duration_marker="5 hours",
        prerequisite_marker="No prerequisites",
        delivery_mode="online",
    )


def valid_page(title="Practical SQL", skill="SQL"):
    return (
        f'<html lang="en"><head><title>{title}</title></head>'
        f"<body><h1>{title}</h1><p>Learn {skill}.</p>"
        "<p>5 hours. No prerequisites. Enroll for free.</p></body></html>"
    ).encode()


def data_analyst_profile_and_match():
    profile = create_profile(
        "synthetic:reskilling_test",
        ["Python", "SQL"],
        desired_role_id="role:data_analyst",
    )
    match = next(
        row for row in match_roles(profile) if row.role_id == "role:data_analyst"
    )
    return profile, match

class TestCourseSchemasAndCatalog(unittest.TestCase):
    def test_unknown_price_cannot_become_a_verified_course(self):
        payload = make_course("course:sql", ["skill:sql"]).model_dump()
        payload["cost"] = None
        with self.assertRaises(ValidationError):
            VerifiedCourse.model_validate(payload)

        with self.assertRaises(ValidationError):
            CourseCost(
                access="paid",
                amount=20,
                currency=None,
                includes_certificate=True,
            )

    def test_duplicate_ids_urls_and_invalid_cache_are_rejected(self):
        course = make_course("course:sql", ["skill:sql"])
        duplicate_url = make_course("course:sql_copy", ["skill:sql"])
        duplicate_url = duplicate_url.model_copy(
            update={"course_url": course.course_url}
        )
        with self.assertRaises(ValidationError):
            CourseCatalog(courses=[course, duplicate_url])

        with TemporaryDirectory() as directory:
            path = Path(directory) / "courses.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(CourseCatalogError):
                CourseCatalogStore(path).load()

    def test_combined_provider_catalog_and_sector_selection(self):
        catalog = CourseCatalogStore().load()
        self.assertEqual(len(catalog.trusted_providers), 15)
        technology = trusted_providers_for_sector(
            catalog, "sector:information_services"
        )
        identifiers = {provider.provider_id for provider in technology}
        self.assertIn("provider:coursera", identifiers)
        self.assertIn("provider:microsoft_learn", identifiers)

    def test_course_updates_preserve_provider_configuration(self):
        original = CourseCatalogStore().load()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "courses.json"
            path.write_text(
                json.dumps(original.model_dump(mode="json")), encoding="utf-8"
            )
            saved = CourseCatalogStore(path).save(
                [make_course("course:statistics", ["skill:statistics"])]
            )
        self.assertEqual(saved.trusted_providers, original.trusted_providers)
        self.assertEqual(saved.provider_groups, original.provider_groups)

class TestCourseValidation(unittest.TestCase):
    def test_valid_course_is_admitted_with_audit_log(self):
        def fetcher(_):
            return FetchedPage(
                "https://example.com/practical-sql",
                valid_page(),
                NOW,
            )

        outcome = validate_course_candidate(make_candidate(), fetcher=fetcher)
        self.assertEqual(outcome.log.status, "verified")
        self.assertIsNotNone(outcome.course)
        self.assertTrue(all(check.passed for check in outcome.log.checks))
        self.assertEqual(outcome.course.last_verified_at, NOW)

    def test_unknown_price_is_withheld_not_treated_as_free(self):
        def fetcher(_):
            return FetchedPage(
                "https://example.com/practical-sql",
                valid_page(),
                NOW,
            )

        outcome = validate_course_candidate(
            make_candidate(cost=False), fetcher=fetcher
        )
        self.assertEqual(outcome.log.status, "withheld")
        self.assertIsNone(outcome.course)
        self.assertIn(
            "cost",
            {check.name for check in outcome.log.checks if not check.passed},
        )

    def test_nonexistent_or_broken_course_is_rejected(self):
        def broken_fetcher(_):
            raise ValueError("Course page could not be fetched safely")

        outcome = validate_course_candidate(
            make_candidate(), fetcher=broken_fetcher
        )
        self.assertEqual(outcome.log.status, "rejected")
        self.assertIsNone(outcome.course)
        self.assertEqual(outcome.log.checks[0].name, "page_fetch")

    def test_unrelated_title_or_skill_page_is_rejected(self):
        def fetcher(_):
            return FetchedPage(
                "https://example.com/practical-sql",
                valid_page(title="Cooking Basics", skill="cooking"),
                NOW,
            )

        outcome = validate_course_candidate(make_candidate(), fetcher=fetcher)
        self.assertEqual(outcome.log.status, "rejected")
        failed = {check.name for check in outcome.log.checks if not check.passed}
        self.assertIn("course_title", failed)
        self.assertIn("skill_coverage", failed)

    def test_batch_validation_obeys_the_candidate_budget(self):
        calls = []

        def broken_fetcher(url):
            calls.append(url)
            raise ValueError("unavailable")

        candidates = [
            make_candidate(
                title=f"SQL Course {index}",
                url=f"https://example.com/sql-{index}",
            )
            for index in range(5)
        ]
        outcomes = validate_course_candidates(
            candidates,
            max_candidates=2,
            fetcher=broken_fetcher,
        )
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(len(calls), 2)

class WiderOnlySearchProvider:
    def __init__(self):
        self.requests: list[CourseSearchRequest] = []
        self.pages: dict[str, bytes] = {}

    def search(self, request):
        self.requests.append(request)
        if request.source_tier == "trusted":
            return []
        slug = request.skill_id.split(":", 1)[1].replace("_", "-")
        url = f"https://example.com/{slug}-essentials"
        title = f"{request.skill_label} Essentials"
        self.pages[url] = valid_page(title=title, skill=request.skill_label)
        return [
            CourseCandidate(
                title=title,
                provider="Example University",
                course_url=url,
                provider_domains=["example.com"],
                source_tier="wider_web",
                skill_ids=[request.skill_id],
                coverage_strength={request.skill_id: 1.0},
                cost=CourseCost(
                    access="free", amount=0, includes_certificate=False
                ),
                duration=CourseDuration(
                    hours=5,
                    display_text="5 hours",
                    basis="provider_stated",
                ),
                duration_marker="5 hours",
                prerequisite_marker="No prerequisites",
                delivery_mode="online",
            )
        ]

    def fetch(self, url):
        return FetchedPage(url, self.pages[url], NOW)


class TestLearningPlanner(unittest.TestCase):
    def test_scenario_priority_is_used_once_and_profile_values_are_preserved(self):
        profile, match = data_analyst_profile_and_match()
        with TemporaryDirectory() as directory:
            result = build_learning_plan(
                profile,
                match,
                "rapid_ai_change",
                country="Malaysia",
                preferred_language="English",
                course_store=CourseCatalogStore(
                    Path(directory) / "courses.json"
                ),
                target_candidates_per_skill=1,
                generated_at=NOW,
            )

        priorities = {
            gap.skill_id: gap for gap in result.plan.prioritized_gaps
        }
        statistics = priorities["skill:statistics"]
        self.assertEqual(statistics.baseline_priority, 0.8)
        self.assertEqual(statistics.applied_adjustment, 0.2)
        self.assertEqual(statistics.adjusted_priority, 1.0)
        self.assertEqual(result.plan.fit_score, match.fit_score)
        self.assertEqual(result.plan.reviewed_skills, profile.skills)
        self.assertEqual(
            set(result.plan.uncovered_skill_ids),
            {gap.skill_id for gap in match.missing_skills},
        )

    def test_set_cover_prerequisites_costs_and_milestones(self):
        profile, match = data_analyst_profile_and_match()
        resources = [
            make_course("course:spreadsheet_foundation", ["skill:spreadsheets"]),
            make_course(
                "course:analysis_bundle",
                ["skill:statistics", "skill:data_visualization"],
                prerequisites=["skill:spreadsheets"],
            ),
            make_course(
                "course:communication",
                ["skill:communication"],
                access="paid",
                amount=10,
                currency="MYR",
            ),
            make_course(
                "course:duplicate_statistics",
                ["skill:statistics"],
                hours=20,
            ),
        ]
        with TemporaryDirectory() as directory:
            store = CourseCatalogStore(Path(directory) / "courses.json")
            store.save(resources)
            result = build_learning_plan(
                profile,
                match,
                "baseline",
                country="Malaysia",
                preferred_language="English",
                course_store=store,
                target_candidates_per_skill=1,
                generated_at=NOW,
            )

        plan = result.plan
        selected = [course.course_id for course in plan.selected_courses]
        self.assertEqual(
            selected,
            [
                "course:spreadsheet_foundation",
                "course:analysis_bundle",
                "course:communication",
            ],
        )
        self.assertNotIn("course:duplicate_statistics", selected)
        self.assertEqual(plan.uncovered_skill_ids, [])
        self.assertEqual(
            [milestone.stage for milestone in plan.milestones],
            ["foundations", "core_skills"],
        )
        self.assertEqual(plan.total_estimated_hours, 15)
        self.assertEqual(plan.cost_totals[0].currency, "MYR")
        self.assertEqual(plan.cost_totals[0].amount, 10)

    def test_circular_prerequisites_are_not_recommended(self):
        profile, match = data_analyst_profile_and_match()
        resources = [
            make_course(
                "course:statistics_cycle",
                ["skill:statistics"],
                prerequisites=["skill:communication"],
            ),
            make_course(
                "course:communication_cycle",
                ["skill:communication"],
                prerequisites=["skill:statistics"],
            ),
            make_course(
                "course:visualization",
                ["skill:data_visualization"],
            ),
        ]
        with TemporaryDirectory() as directory:
            store = CourseCatalogStore(Path(directory) / "courses.json")
            store.save(resources)
            plan = build_learning_plan(
                profile,
                match,
                "baseline",
                country="Malaysia",
                preferred_language="English",
                course_store=store,
                target_candidates_per_skill=1,
                generated_at=NOW,
            ).plan

        selected = {course.course_id for course in plan.selected_courses}
        self.assertEqual(selected, {"course:visualization"})
        self.assertEqual(
            set(plan.uncovered_skill_ids),
            {"skill:statistics", "skill:communication"},
        )

    def test_trusted_first_then_wider_web_fallback(self):
        profile, match = data_analyst_profile_and_match()
        provider = WiderOnlySearchProvider()
        with TemporaryDirectory() as directory:
            result = build_learning_plan(
                profile,
                match,
                "baseline",
                country="Malaysia",
                preferred_language="English",
                course_store=CourseCatalogStore(
                    Path(directory) / "courses.json"
                ),
                search_provider=provider,
                fetcher=provider.fetch,
                target_candidates_per_skill=1,
                generated_at=NOW,
            )

        self.assertEqual(result.plan.uncovered_skill_ids, [])
        self.assertEqual(len(result.validation_logs), 3)
        self.assertTrue(
            all(log.status == "verified" for log in result.validation_logs)
        )
        tiers_by_skill = {}
        for request in provider.requests:
            tiers_by_skill.setdefault(request.skill_id, []).append(
                request.source_tier
            )
        for gap in match.missing_skills:
            self.assertEqual(
                tiers_by_skill[gap.skill_id], ["trusted", "wider_web"]
            )

    def test_invalid_cache_is_not_overwritten(self):
        profile, match = data_analyst_profile_and_match()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "courses.json"
            original = b"{not valid json"
            path.write_bytes(original)
            result = build_learning_plan(
                profile,
                match,
                "baseline",
                country="Malaysia",
                preferred_language="English",
                course_store=CourseCatalogStore(path),
                target_candidates_per_skill=1,
                generated_at=NOW,
            )
            self.assertEqual(path.read_bytes(), original)
        self.assertTrue(
            any("not overwritten" in warning for warning in result.plan.warnings)
        )

class TestSDGMappings(unittest.TestCase):
    def test_curated_rules_cover_current_roles_without_overclaiming(self):
        rules = load_sdg_rules()
        cases = {
            "role:data_analyst": ["skill:statistics"],
            "role:business_analyst": ["skill:requirements_analysis"],
            "role:it_support_specialist": ["skill:it_troubleshooting"],
        }
        for role_id, skills in cases.items():
            with self.subTest(role_id=role_id):
                connections = map_sdg_connections(
                    role_id, skills, rules=rules
                )
                self.assertEqual(
                    {connection.target_id for connection in connections},
                    {"4.4", "8.2"},
                )
                self.assertTrue(
                    all(
                        "sdgs.un.org" in str(connection.evidence_url)
                        for connection in connections
                    )
                )

    def test_unsupported_mapping_is_omitted(self):
        rules = SDGRuleSet(
            rules=[
                SDGRule(
                    rule_id="sdg_rule:sql_4_4",
                    skill_ids=["skill:sql"],
                    sdg_id="SDG 4",
                    target_id="4.4",
                    contribution="direct",
                    rationale="Builds a relevant technical skill.",
                    evidence_url="https://sdgs.un.org/goals/goal4",
                )
            ]
        )
        self.assertEqual(
            map_sdg_connections(
                "role:data_analyst", ["skill:communication"], rules=rules
            ),
            [],
        )

    def test_non_un_evidence_and_mismatched_target_are_rejected(self):
        base = {
            "rule_id": "sdg_rule:invalid",
            "skill_ids": ["skill:sql"],
            "sdg_id": "SDG 4",
            "target_id": "4.4",
            "contribution": "direct",
            "rationale": "Test rule.",
            "evidence_url": "https://example.com/goal4",
        }
        with self.assertRaises(ValidationError):
            SDGRule.model_validate(base)
        base["evidence_url"] = "https://sdgs.un.org/goals/goal4"
        base["target_id"] = "8.2"
        with self.assertRaises(ValidationError):
            SDGRule.model_validate(base)


if __name__ == "__main__":
    unittest.main()
