# Real-catalog backend migration — Persons 2, 3 and 4

**Implemented.** The matching, outlook/evidence and learning-plan backends now
support the real O*NET 0.2 catalog together. `CareerBackend` selects one cached
real snapshot for every operation. The original mock functions remain available
for their existing fixtures and regression tests.

**Person 5 is excluded at the user's request.** No UI, HTTP routes, application
entry point, Replit launch configuration or web dependencies were changed by
this migration. The previously delivered framework-independent Person 1 read
adapters remain available. The UI owner can call the backend interfaces below.

## One shared backend

```python
from src.backend import CareerBackend

backend = CareerBackend()
profile = backend.create_profile(
    "synthetic:example",
    ["Python", "SQL", "Critical Thinking"],
    desired_role_id="role:onet_15_2051_01",
)
matches = backend.match(profile, top_n=10)
outlook = backend.outlook("role:onet_15_2051_01", "baseline")
result = backend.learning_plan(profile, "role:onet_15_2051_01")
response = result.model_dump(mode="json")
```

`python -m src.backend` regenerates `data/demo/onet_backend.json`, an offline
fictional-profile example with baseline and hypothetical rapid-change output.
The fixed demo timestamp is for reproducibility, not a claim of course checking.
No paid model or external API is invoked by that command.

## Contract and identifier changes

| Legacy mock | Real-catalog backend |
|---|---|
| Role catalog 0.1, three roles | Catalog 0.2, 910 occupations |
| `role:data_analyst` | Stable source code, e.g. `role:onet_15_2051_01` |
| `sector_id` / `sector` | `family_id` / `family` — SOC occupational group, not industry |
| Flat tool/general requirements | General `role_skills`, separate `software_associations` |
| Populated mock task-skill links | Imported tasks explicitly unmapped; no automatic task-transfer credit |
| `RoleMatch` / `reviewed_fit_v2` | `OnetRoleMatch` / `reviewed_onet_fit_v3` |
| Legacy learning plan 0.1 | `OnetLearningPlan` 0.2 with software selection and family metadata |

O*NET element identities become `skill:onet_2_a_2_a`, etc. Source task 16150
becomes `task:onet_16150`. Software categories use `group:onet_2_e_6_m`, etc.
Software tool IDs use stable normalized-name hashes, with a small explicit
exact-name map. Python and SQL retain their existing IDs; Excel is explicitly
`skill:microsoft_excel`, not the mock's generic spreadsheets skill.

No role or skill is silently remapped because its name sounds similar. Existing
mock evidence and course/SDG mappings do not become real O*NET mappings.

## Person 2 — intake and matching

- Typed and CV intake accept the new taxonomy. Typed entries remain self-reported;
  CV claims remain unverified until `backend.review_profile(profile, skills)`.
- `match_roles(profile, catalog=real_catalog())` dispatches to `OnetMatcher`.
  Reuse `CareerBackend` or an `OnetMatcher` instance to avoid repeated indexing.
- The result carries catalog/profile fingerprints, canonical family metadata,
  general matched/missing skills, optional software learning choices, and a
  complete component breakdown. Software choices are never silently inserted
  into the general gap list.
- Unknown levels are not mapped to O*NET Level ratings. Group familiarity does
  not grant proficiency or exact possession of an alternative tool.
- Direct general requirements use Importance/5 after relevance selection.
  Software group coverage and exact in-demand tool coverage are separate.
- With both categories present, equal-share defaults combine general/software,
  and group/exact components. These are provisional application assumptions.
  When no In Demand software signals exist, general coverage receives all weight.
- Exact recognized occupation titles, aliases and family names can provide a
  separately explained preference contribution: 90% readiness plus 10%
  preference. Without recognized interests, readiness gets 100%. Desired-role
  selection never boosts score; top-N pinning retains its original rank.
- Old 25% task-transfer credit is disabled for this catalog because imported
  task-to-skill links are absent. It is not added on top of group familiarity.

The core coverage formulas and experiments remain documented in
[Person 1 evaluation](PERSON_1_EVALUATION.md).

## Person 3 — evidence, outlooks, refresh and scenarios

`get_outlook(role_id, ..., catalog=catalog)` and
`get_evidence_chain_response(role_id, ..., catalog=catalog)` use the explicitly
supplied snapshot. Real O*NET role IDs also select the real catalog when no
catalog is supplied. Ledger validation rejects stale task IDs and mixed-catalog
references. No mock source-to-task interpretations were automatically copied.

The real ledger is `data/processed/onet/31.0/trend_signals.json`. It now contains
the [Role 3 BI evidence handoff](ROLE_3_ONET_HANDOFF.md): one live-verified finding
and two contextual task interpretations. Unsupported tasks and occupations still
report insufficient evidence. Catalog record dates remain separate from source
publication/retrieval dates. Imported task-to-skill links remain unmapped, so no
skill evidence chain or evidence-derived numerical adjustment is claimed.

The separate `data/synthetic/onet_scenarios.json` contains two explicit,
team-authored hypothetical stress tests for Business Intelligence Analysts.
They reference its real task/skill IDs, adjust learning priorities only and
never change personal fit. Other occupations currently expose baseline only;
unsupported scenario requests fail explicitly rather than borrowing another
occupation's scenario. `OnetRoleOutlook.available_scenarios` makes this visible.

Refresh supports explicit real-catalog selection:

```python
from src.ingestion.selection import real_catalog
from src.intelligence.feeds import refresh_evidence

# reviewed_source.json must already have valid reviewed source/task references.
result = refresh_evidence(
    review_path="reviewed_source.json", catalog=real_catalog()
)
```

The CLI equivalent adds `--catalog onet`. Real refresh defaults to the separate
ledger and `data/snapshots/trends/onet/` history. Source allowlists, grounding,
review/approval checks, cached failure behavior and publication-date checks are
preserved. This migration does not run a live source refresh or approve findings.

The approval workflow validates real role/task IDs and selects the separate
ledger when a prepared mapping identifies a real role. Generative proposal
contexts accept real catalogs and use only the finding's reviewed task scope
(up to the existing bounded limit), never every task across a broad occupation.
Unmapped role skills remain explicitly unsupported. No paid call or fabricated
accepted task-skill edge is needed to migrate the workflow.

## Person 4 — planning, providers, budgets and SDGs

`build_learning_plan(profile, onet_match, ..., catalog=real_catalog())` accepts
`OnetRoleMatch`, recomputes it to reject stale/tampered scores, and uses the same
catalog for its default outlook. Passing a mismatched catalog/result is rejected.
The selected match's fit score is retained.

The learning plan includes general gaps by default. Unmatched software remains
an option, not an instruction to learn every occupation example. Explicit choice:

```python
match = backend.matcher.match_role(profile, "role:onet_15_2051_01")
choices = [match.software_learning_options[0].skill_id]
result = backend.learning_plan(
    profile, match.role_id, selected_software_skill_ids=choices
)
```

Only currently unmatched in-demand options may be selected. They receive an
explicit authored learning priority of 0.5, not a claimed O*NET tool importance.
Their IDs remain separate in the output. The original match is not mutated.

Real plans use separate `data/processed/onet/31.0/courses.json` and
`sdg_mappings.json` files. Provider groups now support occupational-family IDs;
search requests carry `family_id` and the relevant trusted-provider domains.
Course evidence is matched against the new canonical taxonomy and exact aliases.

MYR budgets apply to the combined selected course/prerequisite closure. If no
budget is provided, only verified zero-cost access routes are eligible. Paid
foreign-currency routes are withheld instead of guessing exchange rates. The
original mixed-currency behavior is retained only for legacy mock calls.

The migrated cache contains provider configuration and **no verified courses**.
The planner returns real general-gap learning objectives with
`verified_resource_not_found` rather than invented course names, URLs, fees or
prerequisites. A search provider can still be injected; all existing validation
and prerequisite/cycle checks remain in force.

A new SDG 4.4 mapping covers employment-related skill preparation, explicitly
as an inferred training connection, not measured employment or SDG impact.
Legacy occupation-specific SDG 8 mappings were not relabeled as real evidence.
Short courses do not establish education, licensing or experience eligibility.

## Verification and remaining scope

Run:

```bash
python -m src.backend
python -m unittest discover -s tests -v
```

The migration adds integration coverage for catalog dispatch, score components,
rank pinning, isolated evidence, scoped scenarios, refresh, software selection,
unchanged fit, stale/tampered results, budget/currency limits and provider families.
Original mock regression tests remain in the suite. Custom matching policy
weights are forwarded through `backend.learning_plan(..., policy=policy)` so
its fit score stays consistent with matching under that policy.

Actual verification: **160 tests passed** (149 existing plus 11 migration
integration tests). Static checks passed for the changed Python files. The
offline backend demo regenerated successfully. Person 5 entry point,
configuration, dependencies and read-adapter files match their pre-migration
versions; no new UI or HTTP files are included.

**Remaining product work, distinct from backend migration:** Person 5's UI/HTTP
adoption (excluded); actual course discovery/verification; reviewed evidence for
additional real roles; independent score calibration and any future
knowledge/abilities/qualification data. No live deployment or evidence coverage
for all 910 roles is claimed.
