"""Exercise general-skill scoring across the real catalog, without AI requests.

Run: python -m scripts.stress_general_fulfilment
Only synthetic profiles and aggregate results are saved.
"""

import json
import time
from pathlib import Path

from src.ingestion.selection import real_catalog
from src.profiles.intake import create_profile
from src.profiles.onet_matching import OnetMatcher


def run():
    started = time.perf_counter()
    catalog = real_catalog()
    matcher = OnetMatcher(catalog)
    core = create_profile('synthetic:stress_core', [s.label for s in catalog.taxonomy.skills if s.kind == 'general'], catalog=catalog)
    previous = {}
    results = []
    checks = 0
    for level in ('unknown', 'beginner', 'intermediate', 'advanced'):
        profile = core.model_copy(update={'skills': [s.model_copy(update={'level': level}) for s in core.skills]})
        rows = matcher.match(profile)
        scores = {row.role_id: row.score_breakdown.general_fulfilment for row in rows}
        assert all(0 <= value <= 1 for value in scores.values())
        if previous:
            assert all(scores[key] + 1e-10 >= value for key, value in previous.items())
        if level != 'unknown':
            assert all(value > 0 for value in scores.values()), 'Known core levels must earn credit for every occupation'
        assert all(0 <= row.fit_score <= 100 for row in rows)
        results.append({'profile': f'all_35_core_skills_{level}', 'roles': len(rows),
            'zero_count': sum(value == 0 for value in scores.values()),
            'minimum_percent': round(min(scores.values()) * 100, 3),
            'maximum_percent': round(max(scores.values()) * 100, 3)})
        previous = scores
        checks += len(rows)
    for name, profile in (
        ('unconfirmed_core', core.model_copy(update={'skills': [s.model_copy(update={'level': 'advanced', 'confirmation': 'unverified'}) for s in core.skills]})),
        ('tools_only', create_profile('synthetic:stress_tools', ['Python', 'SQL', 'Tableau', 'Microsoft Excel'], catalog=catalog)),
        ('empty', create_profile('synthetic:stress_empty', [], catalog=catalog)),
    ):
        rows = matcher.match(profile)
        assert all(row.score_breakdown.general_fulfilment == 0 for row in rows)
        results.append({'profile': name, 'roles': len(rows), 'zero_count': len(rows)})
        checks += len(rows)
    # Each role's exact requirement list, checked independently of a global skill set.
    for role in catalog.roles:
        entries = [matcher.skills[row.skill_id].label for row in matcher.index.general[role.role_id]]
        profile = create_profile('synthetic:stress_role', entries, catalog=catalog)
        profile = profile.model_copy(update={'skills': [s.model_copy(update={'level': 'advanced'}) for s in profile.skills]})
        result = matcher.match_role(profile, role.role_id)
        assert result.score_breakdown.general_fulfilment > 0
        assert 0 <= result.score_breakdown.general_fulfilment <= 1
        checks += 1
    return {'catalog_roles': len(catalog.roles), 'role_profile_comparisons': checks,
        'passed': True, 'elapsed_seconds': round(time.perf_counter() - started, 3),
        'checks': ['scores bounded', 'core fulfilment increases monotonically with levels',
            'known core levels earn positive credit for every role', 'unconfirmed, empty and tool-only profiles earn no general credit',
            'role-specific requirement profiles earn positive credit'], 'results': results}


if __name__ == '__main__':
    result = run()
    path = Path('.trend-cache/general-fulfilment-stress.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
