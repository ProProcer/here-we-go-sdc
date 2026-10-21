"""Real-catalog matching, with bounded group credit and exact-tool evidence."""

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from src.ingestion.coverage import CoverageIndex
from src.ingestion.onet import normalized
from src.profiles.intake import validate_profile
from src.schemas.onet import CoveragePolicy, OnetCatalog
from src.schemas.onet_profile import (
    OnetRoleMatch,
    OnetScoreBreakdown,
    SoftwareLearningOption,
)
from src.schemas.profile import SkillContribution, SkillsProfile


def profile_fingerprint(profile: SkillsProfile) -> str:
    return hashlib.sha256(
        json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


class OnetMatcher:
    """Build once per application worker and reuse the validated catalog index."""

    def __init__(self, catalog: OnetCatalog):
        self.catalog = catalog
        self.index = CoverageIndex(catalog)
        self.fingerprint = hashlib.sha256(
            catalog.model_dump_json().encode()
        ).hexdigest()
        self.skills = {s.skill_id: s for s in catalog.taxonomy.skills}
        self.families = {
            f.family_id: f.label for f in catalog.taxonomy.occupational_families
        }
        self.interest_roles = defaultdict(set)
        for role in catalog.roles:
            for name in [role.role_title, *role.aliases, self.families[role.family_id]]:
                self.interest_roles[normalized(name)].add(role.role_id)

    def _validated(self, profile):
        return validate_profile(
            SkillsProfile.model_validate(profile.model_dump()), self.catalog
        )

    def _match(self, role_id, profile, available, fingerprint, policy):
        coverage = self.index.score(role_id, available, policy)
        role = self.index.roles[role_id]
        supported = {s.skill_id: s for s in profile.skills if s.skill_id in available}
        recognized = {
            normalized(i)
            for i in profile.interests
            if normalized(i) in self.interest_roles
        }
        matching = sorted(i for i in recognized if role_id in self.interest_roles[i])
        preference = len(matching) / len(recognized) if recognized else None
        readiness = coverage.score / 100
        readiness_weight = 0.9 if preference is not None else 1.0
        preference_weight = 0.1 if preference is not None else 0.0
        raw = 100 * (
            readiness_weight * readiness + preference_weight * (preference or 0)
        )
        matched, missing = [], []
        for requirement in self.index.general[role_id]:
            skill = supported.get(requirement.skill_id)
            contribution = SkillContribution(
                skill_id=requirement.skill_id,
                label=self.skills[requirement.skill_id].label,
                importance=requirement.importance,
                coverage=int(skill is not None),
                weighted_contribution=requirement.importance if skill else 0,
                evidence=skill.evidence if skill else [],
                reason="Self-reported or reviewed claim; proficiency is unassessed."
                if skill
                else "Not confirmed in the reviewed profile; not proof of inability.",
            )
            (matched if skill else missing).append(contribution)
        associations = self.index.software[role_id]
        options = []
        for sid in coverage.software_learning_options:
            group_ids = sorted({a.group_id for a in associations if a.skill_id == sid})
            options.append(
                SoftwareLearningOption(
                    skill_id=sid,
                    label=self.skills[sid].label,
                    group_ids=group_ids,
                    group_familiarity_evidenced=any(
                        g in coverage.group_matches for g in group_ids
                    ),
                )
            )
        warnings = [
            *profile.warnings,
            *coverage.warnings,
            "Task-based transfer credit is disabled: imported task-to-skill mappings are unavailable.",
            "Preferences use exact occupation titles, aliases or occupational-family labels; target-role pinning never increases scores.",
        ]
        if not available:
            warnings.append(
                "No supported skills supplied; review claims before interpreting ranking."
            )
        return OnetRoleMatch(
            catalog_fingerprint=self.fingerprint,
            profile_fingerprint=fingerprint,
            role_id=role_id,
            role_title=role.role_title,
            occupation_code=role.occupation_code,
            family_id=role.family_id,
            family=self.families[role.family_id],
            rank=1,
            fit_score=float(
                Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ),
            score_breakdown=OnetScoreBreakdown(
                coverage=coverage,
                readiness=readiness,
                preferences=preference,
                readiness_weight=readiness_weight,
                preference_weight=preference_weight,
                unrounded_score=raw,
            ),
            matched_skills=sorted(matched, key=lambda s: s.skill_id),
            missing_skills=sorted(missing, key=lambda s: s.skill_id),
            software_learning_options=options,
            matched_interests=matching,
            manually_selected=profile.desired_role_id == role_id,
            warnings=list(dict.fromkeys(warnings)),
        )

    def match(
        self,
        profile: SkillsProfile,
        *,
        top_n: int | None = None,
        policy: CoveragePolicy | None = None,
    ) -> list[OnetRoleMatch]:
        if top_n is not None and (
            isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1
        ):
            raise ValueError("top_n must be a positive integer")
        profile = self._validated(profile)
        policy = CoveragePolicy.model_validate(
            (policy or CoveragePolicy()).model_dump()
        )
        available = {
            s.skill_id
            for s in profile.skills
            if s.confirmation in {"self_reported", "confirmed"}
        }
        fingerprint = profile_fingerprint(profile)
        rows = [
            self._match(r.role_id, profile, available, fingerprint, policy)
            for r in self.catalog.roles
        ]
        rows.sort(key=lambda r: (-r.score_breakdown.unrounded_score, r.role_id))
        rows = [r.model_copy(update={"rank": i}) for i, r in enumerate(rows, 1)]
        if top_n is None:
            return rows
        selected = rows[:top_n]
        target = next((r for r in rows[top_n:] if r.manually_selected), None)
        if target is not None:
            selected.append(target.model_copy(update={"pinned": True}))
        return selected

    def match_role(
        self,
        profile: SkillsProfile,
        role_id: str,
        *,
        policy: CoveragePolicy | None = None,
    ) -> OnetRoleMatch:
        profile = self._validated(profile)
        policy = CoveragePolicy.model_validate(
            (policy or CoveragePolicy()).model_dump()
        )
        available = {
            s.skill_id
            for s in profile.skills
            if s.confirmation in {"self_reported", "confirmed"}
        }
        return self._match(
            role_id, profile, available, profile_fingerprint(profile), policy
        )
