"""Reference grouped coverage for Person 2; never silently replaces their fit policy."""

from collections import defaultdict
from collections.abc import Iterable

from src.profiles.intake import validate_profile
from src.schemas.onet import CatalogCoverage, CoveragePolicy, OnetCatalog
from src.schemas.profile import SkillsProfile


class CoverageIndex:
    """Index once per validated snapshot, rather than scanning it for every role."""

    def __init__(self, catalog: OnetCatalog):
        self.catalog = catalog
        self.roles = {r.role_id: r for r in catalog.roles}
        self.skill_ids = {s.skill_id for s in catalog.taxonomy.skills}
        self.general = defaultdict(list)
        self.software = defaultdict(list)
        for requirement in catalog.role_skills:
            self.general[requirement.role_id].append(requirement)
        for association in catalog.software_associations:
            self.software[association.role_id].append(association)

    def score(
        self,
        role_id: str,
        reviewed_skill_ids: Iterable[str],
        policy: CoveragePolicy | None = None,
    ) -> CatalogCoverage:
        """Score presence of reviewed claims, never infer proficiency from a name."""
        if role_id not in self.roles:
            raise KeyError(f"Unknown O*NET role: {role_id}")
        policy = policy or CoveragePolicy()
        available = set(reviewed_skill_ids)
        unknown = available - self.skill_ids
        if unknown:
            raise ValueError(f"Unknown reviewed skill IDs: {sorted(unknown)}")
        requirements = self.general[role_id]
        total = sum(r.importance for r in requirements)
        if not total:
            raise ValueError("Role has no usable general requirements")
        matched = sorted(r.skill_id for r in requirements if r.skill_id in available)
        general = (
            sum(r.importance for r in requirements if r.skill_id in available) / total
        )
        # Only occupation-specific In Demand examples define scored software signals.
        # The other examples remain available as context and category familiarity evidence.
        associations = self.software[role_id]
        targets = {r.skill_id for r in associations if r.in_demand}
        target_groups = {r.group_id for r in associations if r.in_demand}
        group_members = defaultdict(set)
        for row in associations:
            if row.group_id in target_groups:
                group_members[row.group_id].add(row.skill_id)
        matches = {
            group: sorted(members & available)
            for group, members in sorted(group_members.items())
            if members & available
        }
        warnings = [
            "Exploratory coverage of reviewed skill claims; not hiring probability or proficiency assessment.",
            "Missing profile evidence means unconfirmed, not inability.",
            "Software group credit indicates category familiarity, not interchangeable tools.",
            "Software learning options are alternatives to inspect, not a checklist of mandatory courses.",
            "Equal-share defaults are application assumptions; no empirical calibration is claimed.",
            "Education, licenses and experience are not assessed; high coverage does not establish job eligibility.",
        ]
        exact = groups = software = None
        share = 1.0
        if targets:
            exact = len(targets & available) / len(targets)
            groups = len(matches) / len(target_groups)
            software = policy.group_share * groups + (1 - policy.group_share) * exact
            share = policy.general_share
        else:
            warnings.append(
                "No occupation-specific In Demand software signals; general skills receive all weight. This does not mean software is unnecessary."
            )
        score = share * general + (1 - share) * (software or 0)
        return CatalogCoverage(
            role_id=role_id,
            score=round(100 * min(1.0, max(0.0, score)), 6),
            general_coverage=general,
            software_group_coverage=groups,
            software_exact_coverage=exact,
            software_coverage=software,
            effective_general_share=share,
            policy=policy,
            matched_general_skill_ids=matched,
            unconfirmed_general_skill_ids=sorted(
                r.skill_id for r in requirements if r.skill_id not in available
            ),
            matched_software_skill_ids=sorted(targets & available),
            software_learning_options=sorted(targets - available),
            group_matches=matches,
            warnings=warnings,
        )

    def score_profile(
        self, role_id: str, profile: SkillsProfile, policy: CoveragePolicy | None = None
    ) -> CatalogCoverage:
        profile = validate_profile(
            SkillsProfile.model_validate(profile.model_dump()), self.catalog
        )
        return self.score(
            role_id,
            [
                s.skill_id
                for s in profile.skills
                if s.confirmation in {"self_reported", "confirmed"}
            ],
            policy,
        )
