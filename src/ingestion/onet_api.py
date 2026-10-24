"""Small framework-independent read adapters for Person 5's versioned routes."""

from src.schemas.onet import OnetCatalog


def list_onet_roles(
    catalog: OnetCatalog, *, query: str = "", offset: int = 0, limit: int = 25
) -> dict:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    terms = query.casefold().split()
    rows = [
        role
        for role in catalog.roles
        if all(
            term
            in " ".join(
                [role.role_title, role.occupation_code, *role.aliases]
            ).casefold()
            for term in terms
        )
    ]
    if terms:
        phrase = " ".join(terms)

        def relevance(role):
            title = " ".join(role.role_title.casefold().split())
            # Rank the title people see ahead of matches in alternate titles.
            if title == phrase:
                tier = 0
            elif title.startswith(phrase):
                tier = 1
            elif all(term in title for term in terms):
                tier = 2
            else:
                tier = 3
            return tier, title, role.role_id

        rows.sort(key=relevance)
    return {
        "schema_version": "0.2.0",
        "catalog_id": catalog.catalog_id,
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "roles": [
            {
                "role_id": role.role_id,
                "occupation_code": role.occupation_code,
                "role_title": role.role_title,
                "family_id": role.family_id,
            }
            for role in rows[offset : offset + limit]
        ],
        "attribution": catalog.provenance.attribution,
        "license_url": catalog.provenance.license_url,
    }


def get_onet_role(catalog: OnetCatalog, role_id: str) -> dict:
    role = next((r for r in catalog.roles if r.role_id == role_id), None)
    if role is None:
        raise KeyError(role_id)
    general = [r for r in catalog.role_skills if r.role_id == role_id]
    software = [r for r in catalog.software_associations if r.role_id == role_id]
    skills = {r.skill_id for r in [*general, *software]}
    group_ids = {r.group_id for r in software}
    # Send only this occupation's group members; this is not global equivalence.
    group_members = {}
    for row in software:
        group_members.setdefault(row.group_id, set()).add(row.skill_id)
    return {
        "schema_version": "0.2.0",
        "catalog_id": catalog.catalog_id,
        "role": role.model_dump(mode="json"),
        "general_requirements": [r.model_dump(mode="json") for r in general],
        "software_associations": [r.model_dump(mode="json") for r in software],
        "skills": [
            r.model_dump(mode="json")
            for r in catalog.taxonomy.skills
            if r.skill_id in skills
        ],
        "tasks": [
            r.model_dump(mode="json")
            for r in catalog.taxonomy.tasks
            if r.task_id in role.task_ids
        ],
        "software_groups": [
            {
                **g.model_dump(mode="json"),
                "skill_ids": sorted(group_members[g.group_id]),
            }
            for g in catalog.taxonomy.software_groups
            if g.group_id in group_ids
        ],
        "limitations": catalog.limitations,
        "provenance": catalog.provenance.model_dump(mode="json"),
    }
