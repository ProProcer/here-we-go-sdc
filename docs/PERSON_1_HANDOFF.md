# Person 1: real O*NET catalog handoff

Person 1 now supplies a reproducible, validated O*NET® 31.0 catalog, source
inventory, exclusion audit, paged read adapters, and an exploratory grouped
coverage implementation for Person 2 to integrate. The source data are real;
the demonstration profiles and scoring assumptions are explicitly separate.

The existing synthetic 0.1 catalog and all current default consumers remain
operational. The new catalog uses **schema 0.2.0** because its software signals,
occupational families, and unasserted task-to-skill links cannot truthfully be
represented by the mock's flat requirements. Do not replace `get_roles()` or
feed this catalog to the old matcher without adopting the versioned contract.

## Build and verify

Use Python 3.10+ with the repository's pinned Pydantic dependency:

```bash
python -m pip install -r requirements.txt
python -m src.ingestion.onet
python -m src.ingestion.onet_experiments
python -m src.ingestion.onet_demo
python -m unittest discover -s tests -v
```

All three module commands are offline. The importer checks pinned raw file
hashes and column/row integrity before processing. Output is deterministic;
changing a source file requires a deliberately updated source manifest.

## Delivered data

| Artifact | Contents |
|---|---|
| `data/raw/onet/31.0/manifest.json` | Eight original CSV hashes, row counts and source dictionary URLs |
| `data/processed/onet/31.0/catalog.json` | Validated 0.2 catalog and provenance |
| `data/processed/onet/31.0/audit.json` | Coverage, exclusions and transformation counts |
| `data/experiments/onet/31.0/results.json` | Full-catalog invariants, six-role sample and weight sensitivity |
| `data/demo/onet_coverage.json` | Fictional reviewed profile, real role detail and coverage examples |

The import includes **910 of 1,016 occupations**, **28,335 relevant general
requirements**, **31,194 software observations**, **18,592 task statements**,
and **134 software categories**. Every excluded occupation has explicit reasons:
93 have neither detailed tasks nor skill/software data; 13 have tasks and
software but lack general skill ratings. Raw records are not deleted.

## Core decisions

1. Include occupations with tasks, Essential Skills ratings, Transferable
   Skills ratings, and software examples. Require at least one usable general
   requirement after filtering; fail rather than silently dropping a newly
   inconsistent occupation.
2. Join Importance and Level by occupation code and element ID. Exclude pairs
   with `Not Relevant = Y`; omit unknown relevance and flagged/unknown Importance
   precision. Compute retained importance as **source Importance / 5**.
3. Preserve raw Importance, record month and usable Level. Suppressed Level
   becomes null; **146** such levels are withheld among retained pairs.
   No proficiency comparison is made: self-reported Beginner/Intermediate does
   not have a validated mapping to O*NET's 0–7 occupational Level scale.
4. Retain all software observations and their demand flags. Only occupation-
   specific `In Demand = Y` signals define scored software targets. `N` is
   not interpreted as irrelevant. All software remains visible as context.
5. Use O*NET software categories for **category familiarity**, not equivalence.
   A known role-associated tool can support an in-demand category without
   granting possession of another tool. Do not label this demonstrated task
   proficiency, automatic substitution, or an accepted task-specific mapping.
6. Score general requirements, category familiarity and individual demand
   signals separately. Start with explicit equal-share defaults; these are
   application assumptions, not measured importance or calibrated transfer.
7. When no scored software signals exist, use general coverage alone with a
   coverage warning. **423** occupations use this fallback. An existing
   software target with no reviewed match instead receives zero coverage.
8. Classify by **SOC major occupational family**, not industry. One occupation
   can occur in several industries; guessing an industry would be misleading.
9. Preserve source task statements. The provided tables do not directly link
   individual tasks to skills: `skill_ids=[]`, `mapping_status=unmapped`.
   Co-occurrence is not a task-to-skill mapping. Existing mock mappings remain
   fixtures; they are not silently promoted to observed facts.

## Working Python interfaces

```python
from src.ingestion.onet import load_onet_catalog
from src.ingestion.onet_api import list_onet_roles, get_onet_role
from src.ingestion.coverage import CoverageIndex
from src.profiles.intake import create_profile

catalog = load_onet_catalog()  # parse/validate once, reuse per application worker
page = list_onet_roles(catalog, query="business intelligence", limit=25)
role_id = "role:onet_15_2051_01"
detail = get_onet_role(catalog, role_id)
profile = create_profile(
    "synthetic:example", ["Python", "SQL", "Tableau"], catalog=catalog
)
coverage = CoverageIndex(catalog).score_profile(role_id, profile)
```

The existing typed intake and exact alias normalization work when explicitly
passed this taxonomy. Claims still require self-report/review; levels stay
unknown. Coverage rejects unknown IDs and uncanonical profile labels.

`get_onet_roles()` also returns the complete JSON-compatible catalog for offline
consumers. Use the paged list/detail adapters for HTTP delivery rather than
transferring the full snapshot on every request. No HTTP server is added.

## What changes for teammates

| Owner | Required adoption work |
|---|---|
| Person 2 | Select the 0.2 catalog explicitly; consume separate general/software data. Reuse `CoverageIndex` or port its documented policy, retain all score components, and integrate transfer/preferences without counting group familiarity twice. Never use the existing flat matcher on this catalog. |
| Person 3 | Use source occupation/task IDs and map evidence to actual imported tasks. Treat unmapped skills and roles without reviewed evidence as insufficient evidence. Existing three-role scenarios/ledgers do not automatically cover the 910 roles. |
| Person 4 | Preserve Person 2's reviewed gaps. General gaps can be learning objectives; software signals are optional learning candidates, not all mandatory courses. Adopt new IDs in course/SDG data and request an outlook using the same catalog. Do not promise eligibility for licensed/degree-gated occupations from short courses. |
| Person 5 | Add a versioned catalog selector, paged list/detail routes, family labels, attribution, source dates and separate coverage components. Keep existing mock routes until consumers migrate together. Handle no software signal and unavailable task-skill/outlook evidence explicitly. |

See [the migration guide](PERSON_1_MIGRATION.md) for field changes, IDs,
formulas, safe fallbacks and copyable integration patterns. See
[evaluation](PERSON_1_EVALUATION.md) for actual checks and limitations.

## Research basis and data rights

- [O*NET taxonomy](https://www.onetcenter.org/taxonomy.html): occupation codes and hierarchy.
- [Software Skills dictionary](https://www.onetcenter.org/dictionary/31.0/csv/software_skills.html): examples, categories and binary demand flags.
- [Essential Skills dictionary](https://www.onetcenter.org/dictionary/31.0/csv/essential_skills.html): Importance/Level, precision and relevance fields.
- [SOC major groups](https://www.bls.gov/soc/2018/major_groups.htm): occupational families, distinct from industries.
- [Database license](https://www.onetcenter.org/license_db.html): CC BY 4.0 attribution and disclosure of modifications.

This catalog adapts O*NET 31.0 Database information from USDOL/ETA under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). FutureReady AI made
the transformations described above; USDOL/ETA has not endorsed or tested them.
O*NET® is a trademark of USDOL/ETA. See the raw snapshot README and catalog
provenance for attribution, precise fingerprints and unknown download dates.

U.S. occupational data does not establish Malaysian demand or current job
eligibility. Knowledge, abilities, education, experience and Job Zones are
explicitly outside this first contract; adding them later requires a separate
data and consumer migration, not an implicit assumption in course matching.
