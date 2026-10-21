# Adopting Person 1's 0.2 real catalog

This is a consumer migration guide, not a claim that all teammate modules have
already migrated. Person 1's importer, schema, read adapters, reference coverage
engine and examples are implemented and tested. Existing module defaults still
use the 0.1 synthetic fixture, so their current demonstrations remain repeatable.

## Contract differences

| 0.1 mock | 0.2 real handoff | Required interpretation |
|---|---|---|
| `schema_version=0.1.0` | `schema_version=0.2.0` | Select explicitly; do not silently mix snapshots |
| Three mnemonic role IDs | `role:onet_15_2051_01`, etc. | Stable source-code mapping; title changes do not change IDs |
| `role_title` only | Title, source code, description and aliases | Search aliases but retain canonical role identity |
| `sector_id` / `taxonomy.sectors` | `family_id` / `occupational_families` | SOC occupation family, not industry; update UI and course-provider filters |
| Flat `role_skills` including tools | General-only `role_skills` plus `software_associations` | Software examples are not universal requirements |
| One illustrative importance value | Normalized and source Importance, usable Level, precision flag and month | Do not compare profile levels with occupational Level without calibration |
| Task `skill_ids` always populated | Empty `skill_ids`, `mapping_status=unmapped` | Disable automatic task-based transfer until mappings exist |
| Synthetic source record | Eight source records plus full input provenance | Show CC BY 4.0 attribution, geography and record dates |
| All roles included in fixture | 910 included, 106 explicitly excluded | Exclusions are data coverage, not judgments about career value |

Names and fields are defined in `src/schemas/onet.py`. The complete reference
JSON is `data/processed/onet/31.0/catalog.json`.

## Identifier rules

- Occupation: remove punctuation from the source code with underscores:
  `15-2051.01` becomes `role:onet_15_2051_01`.
- General skill: preserve element identity, e.g. `2.A.2.a` becomes
  `skill:onet_2_a_2_a` (Critical Thinking).
- Task: preserve numeric source task ID: `16150` becomes `task:onet_16150`.
- Software category: preserve source element ID, e.g. `2.E.6.m` becomes
  `group:onet_2_e_6_m`.
- Software identity: SHA-256 prefix of normalized tool name, except a small,
  explicit exact-name map in `SOFTWARE_NAMES`. This is stable across source-row
  reordering. Python and SQL retain `skill:python` and `skill:sql`; Excel is
  `skill:microsoft_excel`, distinct from the mock's generic spreadsheets skill.
- Exact aliases, such as `Power BI` and `Microsoft Power BI`, normalize to one
  tool. They are not the same mechanism as category familiarity or transfer.

The source occupation titles do not establish that the old `role:data_analyst`
is exactly Business Intelligence Analysts, or that generic Business Analyst is
exactly Management Analysts. There is deliberately no automatic role remapping.
Person 3's existing task evidence must be reviewed against actual task text.
Mock `communication`, `statistics` and `data_visualization` also do not acquire
one-to-one O*NET skill equivalents merely because their names are related.

## Reference scoring for Person 2

`CoverageIndex` accepts an explicitly supplied validated 0.2 catalog. Construct
it once per catalog snapshot and reuse it. `score_profile` accepts the existing
reviewed `SkillsProfile`, rejects mismatched labels/unknown IDs, and counts only
`self_reported` or `confirmed` claims. It does not infer proficiency.

Let G be weighted coverage of relevant general requirements using Importance/5.
For this role, let D be the unique `In Demand=Y` software IDs and K their source
software categories. For each category in K, candidate evidence consists only
of software examples associated with this same occupation. Nondemand examples
can support familiarity; they do not become exact in-demand matches.

```text
E = matched IDs in D / number of IDs in D
C = categories in K with at least one reviewed associated tool / number of K
S = group_share * C + (1 - group_share) * E
coverage = 100 * (general_share * G + (1 - general_share) * S)
```

Defaults: `group_share=0.5`, `general_share=0.5`. These are neutral, provisional
application weights, not an empirical result. `CoveragePolicy` permits shares
strictly between 0 and 1; experiments compare 0.25, 0.5 and 0.75.

If D is empty, C/E/S are null and `coverage=100*G`. Missing software source
signals are not personal deficits. If D exists but the person knows no target
or associated category tool, software coverage is zero. Deduplicate profile
claims; one category can be credited at most once. An exact tool supports its
category and its individual component, bounded by the explicit component shares.
An alternative does not grant any other tool's exact match.

This baseline intentionally leaves preference, existing task-transfer bonuses
and level matching out of its result. It returns `score`, not the legacy
`fit_score`, and is labeled `onet_grouped_coverage_v1`. Person 2 must adopt a
new result/breakdown version when combining it with their final matching policy;
do not add the existing 25% task-transfer bonus to category credit by default.
The old `reviewed_fit_v2` response must not be relabeled as this new method.

Useful components in `CatalogCoverage`:

- `general_coverage`, `software_group_coverage`, `software_exact_coverage` and
  `software_coverage`, with applied policy and effective general share.
- `unconfirmed_general_skill_ids`: potential learning objectives, not proof of
  inability.
- `software_learning_options`: unmatched in-demand examples, not a mandatory
  checklist and not automatically the same as Person 2's actual skill gaps.
- `group_matches`: exactly which reviewed tool IDs supported category credit.
- Explicit warnings about qualification, proficiency and geographic limitations.

For future task-specific alternatives, use separate reviewed evidence about the
task and constraints. Power BI/Tableau for a new report is not the same mapping
as modifying existing DAX measures; Docker/Kubernetes are not automatically
substitutes. A coarse category is never an equivalence assertion.

## Person 3: source evidence and scenarios

`get_outlook()` and ledger validation currently load the synthetic catalog
internally. Before migrating, allow explicit catalog injection and validate all
role/task/skill references against the same 0.2 snapshot. Revise baseline labels
that currently always say requirements are synthetic.

Use actual O*NET task IDs for new role evidence. No imported task-to-skill edges
are asserted, so do not manufacture chains or grant skill priorities from the
occupation's shared skill list. Evidence with no reviewed mapping should remain
contextual/unmapped; role-specific outlook should report insufficient evidence.
Historical mock scenarios retain their original IDs and hypothetical labels.
Do not copy them across 910 occupations.

## Person 4: affordable learning plans

The planner currently requires `RoleMatch`, calls the mock-backed outlook loader,
and uses sector-based course-provider selection and mock-based SDG rules.
Passing only `catalog=onet_catalog` does not finish its migration.

Adoption requires:

1. Accept Person 2's new reviewed matching breakdown and preserve its score.
2. Carry general learning gaps separately from optional software opportunities;
   pick task-appropriate tools rather than recommending every unmatched example.
3. Adopt occupational-family metadata in course search/provider selection.
4. Supply an outlook loader using the same catalog and retain explicit
   insufficient-evidence behavior. The existing injected `outlook_loader`
   interface provides a migration seam, not a ready 910-role evidence source.
5. Review course and SDG IDs. Generic training relevance may support SDG 4.4;
   unrelated occupation-specific SDG mappings must not be copied automatically.
6. Retain honest `verified_resource_not_found` behavior when no verified
   affordable course exists. Short courses do not remove license/degree gates.

The actual new course discovery, source verification and SDG curation remain
Person 4's responsibility, not Person 1 catalog completion criteria.

## Person 5: read routes and display

Use `list_onet_roles(catalog, query=..., offset=..., limit=...)` for search and
paging (maximum 100 per page). `get_onet_role(catalog, role_id)` returns only that
role's relevant skills, software, tasks, groups and attribution. Cache the
validated catalog and coverage index per application worker; do not parse the
32 MB snapshot per click.

Suggested routes are `/api/v2/roles` and `/api/v2/roles/{role_id}`. These are
route proposals; the delivered functions have no FastAPI dependency. Keep
`/api/roles` pointed at the mock until coordinated consumer adoption.

Display source geography, release and actual record month, occupation family,
attribution/license link, component coverage and missing-data notes. Never call
category familiarity proficiency or probability of getting hired. A high score
can occur for a regulated occupation while licenses and education are unassessed.

## Joint migration check

All consumers must agree on one catalog ID/version before switching defaults.
Keep original synthetic fixtures for regression tests. Add profile tests for
alternative-only tools, exact matches, no software signal, unknown levels,
unmapped tasks and absent course/evidence coverage. The complete mock-based
suite should still pass alongside the new catalog suite.
