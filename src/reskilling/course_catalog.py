"""Validated JSON repository for learning resources."""

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from src.intelligence.storage import atomic_json
from src.schemas.roadmap import VerifiedCourse
from src.schemas.role import Contract, SkillId

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COURSE_CATALOG = ROOT / "data/processed/courses.json"

ProviderId = Annotated[str, Field(pattern=r"^provider:[a-z0-9_]+$")]
ProviderGroupId = Annotated[str, Field(pattern=r"^provider_group:[a-z0-9_]+$")]


class TrustedProvider(Contract):
    provider_id: ProviderId
    name: str = Field(min_length=1)
    domains: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_domains(self):
        normalized = [domain.strip().casefold() for domain in self.domains]
        if any(
            not domain or "/" in domain or ":" in domain or domain.startswith(".")
            for domain in normalized
        ):
            raise ValueError("Trusted-provider domains must be bare host names")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Trusted-provider domains must be unique")
        return self


class ProviderGroup(Contract):
    group_id: ProviderGroupId
    label: str = Field(min_length=1)
    sector_ids: list[str] = Field(default_factory=list)
    family_ids: list[str] = Field(default_factory=list)
    provider_ids: list[ProviderId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_values(self):
        if len(self.sector_ids) != len(set(self.sector_ids)):
            raise ValueError("Provider-group sector IDs must be unique")
        if len(self.family_ids) != len(set(self.family_ids)):
            raise ValueError("Provider-group family IDs must be unique")
        if len(self.provider_ids) != len(set(self.provider_ids)):
            raise ValueError("Provider-group provider IDs must be unique")
        return self


class CourseCatalog(Contract):
    schema_version: Literal["0.1.0"] = "0.1.0"
    updated_at: datetime | None = None
    trusted_providers: list[TrustedProvider] = Field(default_factory=list)
    provider_groups: list[ProviderGroup] = Field(default_factory=list)
    courses: list[VerifiedCourse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_catalog(self):
        course_ids = [course.course_id for course in self.courses]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("Duplicate course IDs")

        urls = [str(course.course_url) for course in self.courses]
        if len(urls) != len(set(urls)):
            raise ValueError("Duplicate canonical course URLs")

        provider_ids = [provider.provider_id for provider in self.trusted_providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("Duplicate trusted-provider IDs")
        domains = [
            domain.strip().casefold()
            for provider in self.trusted_providers
            for domain in provider.domains
        ]
        if len(domains) != len(set(domains)):
            raise ValueError("A trusted domain may belong to only one provider")
        group_ids = [group.group_id for group in self.provider_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("Duplicate provider-group IDs")
        known_providers = set(provider_ids)
        for group in self.provider_groups:
            unknown = set(group.provider_ids) - known_providers
            if unknown:
                raise ValueError(
                    f"Provider group {group.group_id} has unknown providers: "
                    f"{sorted(unknown)}"
                )

        timestamps = [course.last_verified_at for course in self.courses]
        if self.updated_at is not None:
            timestamps.append(self.updated_at)
        if any(value.utcoffset() is None for value in timestamps):
            raise ValueError("Catalog timestamps must include a UTC offset")
        return self


class CourseCatalogError(ValueError):
    """Raised when a stored course catalog cannot be decoded or validated."""


class CourseCatalogStore:
    """Small replaceable repository backed by one atomically written JSON file."""

    def __init__(self, path: str | Path = DEFAULT_COURSE_CATALOG):
        self.path = Path(path)

    def load(self) -> CourseCatalog:
        if not self.path.exists():
            return CourseCatalog()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return CourseCatalog.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise CourseCatalogError(
                f"Course catalog is unavailable or invalid: {self.path.name}"
            ) from exc

    def save(self, courses: Iterable[VerifiedCourse]) -> CourseCatalog:
        current = self.load()
        ordered = sorted(courses, key=lambda course: course.course_id)
        catalog = CourseCatalog.model_validate(
            {
                "schema_version": "0.1.0",
                "updated_at": datetime.now(UTC),
                "trusted_providers": [
                    provider.model_dump(mode="json")
                    for provider in current.trusted_providers
                ],
                "provider_groups": [
                    group.model_dump(mode="json") for group in current.provider_groups
                ],
                "courses": [course.model_dump(mode="json") for course in ordered],
            }
        )
        atomic_json(self.path, catalog.model_dump(mode="json"))
        return catalog

    def upsert(self, course: VerifiedCourse) -> CourseCatalog:
        current = self.load()
        by_id = {item.course_id: item for item in current.courses}
        by_id[course.course_id] = course
        return self.save(by_id.values())

    def remove(self, course_id: str) -> CourseCatalog:
        current = self.load()
        remaining = [
            course for course in current.courses if course.course_id != course_id
        ]
        return self.save(remaining)


def trusted_providers_for_sector(
    catalog: CourseCatalog, sector_id: str
) -> list[TrustedProvider]:
    """Return general providers plus providers configured for a role sector."""

    selected_ids = []
    for group in catalog.provider_groups:
        if group.group_id == "provider_group:general" or sector_id in group.sector_ids:
            selected_ids.extend(group.provider_ids)
    providers = {
        provider.provider_id: provider for provider in catalog.trusted_providers
    }
    return [
        providers[provider_id]
        for provider_id in dict.fromkeys(selected_ids)
        if provider_id in providers
    ]


def trusted_providers_for_family(
    catalog: CourseCatalog, family_id: str
) -> list[TrustedProvider]:
    selected = {
        pid
        for group in catalog.provider_groups
        if group.group_id == "provider_group:general" or family_id in group.family_ids
        for pid in group.provider_ids
    }
    return [p for p in catalog.trusted_providers if p.provider_id in selected]


def course_is_available(
    course: VerifiedCourse,
    *,
    country: str | None,
    verified_after: datetime | None = None,
) -> bool:
    """Apply location and optional freshness gates without filtering by language."""

    if verified_after is not None:
        if verified_after.utcoffset() is None:
            raise ValueError("verified_after must include a UTC offset")
        if course.last_verified_at < verified_after:
            return False

    if course.delivery_mode == "online":
        return True
    if not country:
        return False
    requested = country.strip().casefold()
    return any(requested == item.strip().casefold() for item in course.country_codes)


def courses_for_skills(
    catalog: CourseCatalog,
    skill_ids: Iterable[SkillId],
    *,
    country: str | None = None,
    preferred_language: str | None = None,
    verified_after: datetime | None = None,
) -> list[VerifiedCourse]:
    """Return relevant courses in a stable coverage-first discovery order."""

    requested = set(skill_ids)
    if not requested:
        return []
    language = preferred_language.strip().casefold() if preferred_language else None

    candidates = [
        course
        for course in catalog.courses
        if requested.intersection(course.skill_ids)
        and course_is_available(course, country=country, verified_after=verified_after)
    ]

    def ranking_key(course: VerifiedCourse):
        coverage = sum(
            course.coverage_strength.get(skill_id, 0) for skill_id in requested
        )
        language_match = bool(
            language is not None and course.language.strip().casefold() == language
        )
        trusted = course.source_tier == "trusted"
        return (
            -coverage,
            -int(language_match),
            -int(trusted),
            course.cost.amount,
            course.duration.hours,
            course.course_id,
        )

    return sorted(candidates, key=ranking_key)
