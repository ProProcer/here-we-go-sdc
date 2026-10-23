"""Exact taxonomy lookup for typed skill entries, not free-text CV extraction."""

import unicodedata

from src.schemas.onet import CatalogTaxonomy
from src.schemas.role import Skill, Taxonomy


def normalize_key(value: str) -> str:
    """Ignore Unicode presentation, case and repeated whitespace."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def skill_index(taxonomy: Taxonomy | CatalogTaxonomy) -> dict[str, Skill]:
    index = {}
    for skill in taxonomy.skills:
        for name in (skill.skill_id, skill.label, *skill.aliases):
            key = normalize_key(name)
            if key in index and index[key].skill_id != skill.skill_id:
                raise ValueError(f"Ambiguous taxonomy alias: {name}")
            index[key] = skill
    # Explicit abbreviations resolve to existing canonical records only.
    for alias, canonical in {"HTML": "Hypertext markup language HTML",
            "CSS": "Cascading style sheets CSS"}.items():
        target = index.get(normalize_key(canonical))
        if target is not None and normalize_key(alias) not in index:
            index[normalize_key(alias)] = target
    return index


def normalize_entries(
    entries: list[str], taxonomy: Taxonomy | CatalogTaxonomy
) -> tuple[list[tuple[Skill, list[str]]], list[str]]:
    """Resolve complete entries; aliases merge without adding scoring credit."""
    index = skill_index(taxonomy)
    found = {}
    unknown = []
    for entry in entries:
        key = normalize_key(entry)
        if not key:
            continue
        skill = index.get(key)
        if skill is None:
            unknown.append(entry)
            continue
        row = found.setdefault(skill.skill_id, (skill, []))
        if entry not in row[1]:
            row[1].append(entry)
    return [found[key] for key in sorted(found)], sorted(set(unknown))
