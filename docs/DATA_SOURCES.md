# Data sources — Person 1 occupation catalog

This inventory covers Person 1's imported occupation data. Person 3's separate
research/evidence inventories remain in their source and handoff files; this
page does not claim to audit every team member's external service or model.

## O*NET® 31.0 Database

- **Owner:** U.S. Department of Labor, Employment and Training Administration
  (USDOL/ETA); developed by the National Center for O*NET Development.
- **Source:** https://www.onetcenter.org/database.html
- **Release:** 31.0, August 2026.
- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), under
  the [O*NET database license](https://www.onetcenter.org/license_db.html).
- **Purpose:** redistribute the source snapshot and adapted occupational
  role/skill/task catalog for educational career exploration.
- **Verification date:** 2026-10-21. **Original download date:** not recorded.
- **Record dates:** individual task/rating months retained; neither the release
  nor verification date is substituted for them. Software observations have no
  per-row date in the supplied table; their provenance is the pinned release.
- **Synthetic:** false for source data. Example user profiles are synthetic;
  normalized weights, category familiarity and scoring policies are application
  transformations rather than source measurements.
- **Location:** `data/raw/onet/31.0/`; exact hashes and original row counts are in
  [`manifest.json`](../data/raw/onet/31.0/manifest.json).
- **Output:** `data/processed/onet/31.0/catalog.json`, used only by explicit 0.2
  loaders/adapters and the demonstration until coordinated team migration.

| Original table | Rows | Use |
|---|---:|---|
| Occupation Data | 1,016 | Occupation code, title, description |
| Job Titles | 54,269 | Alternative role titles |
| Task Statements | 18,838 | Source tasks, types, update months |
| Essential Skills | 18,200 | General Importance/Level ratings and flags |
| Transferable Skills | 45,500 | General Importance/Level ratings and flags |
| Software Skills | 31,821 | Software examples, category IDs and demand flags |
| Content Model Reference | 3,006 | General skill definitions |
| Scales Reference | 33 | Verify IM 1–5 and LV 0–7 bounds |

These are **raw table row counts**, not distinct-skill counts or post-filter
counts. The [handoff](PERSON_1_HANDOFF.md) and generated audit give final counts.
Each table's official dictionary URL is included in the manifest.

Modifications: filter incomplete occupation coverage; normalize stable IDs and
exact aliases; divide relevant Importance by 5; withhold suppressed Level;
retain category/demand metadata separately; leave unprovided task-skill edges
unmapped. The original CSVs are unchanged.

O*NET® is a trademark of USDOL/ETA. FutureReady AI adapts the information;
USDOL/ETA has not approved, endorsed or tested these modifications. The code's
Apache-2.0 license does not relicense third-party data. Downstream pages must
retain attribution and a license link.

Limitations: U.S. occupational descriptions and demand signals do not establish
Malaysian demand. Coverage scores do not establish qualifications, licensing,
proficiency or probability of employment. Record freshness varies.

## SOC major occupational groups

- **Owner/source:** U.S. Bureau of Labor Statistics,
  [2018 SOC major groups](https://www.bls.gov/soc/2018/major_groups.htm).
- **Use:** map occupation-code prefixes to occupational-family labels in
  `src/ingestion/onet.py`; these are not employer industries.
- **Verification date:** 2026-10-21.
- **Rights:** federal government classification information; see
  [BLS linking and copyright policy](https://www.bls.gov/bls/linksite.htm).
- **Synthetic:** false for classification; the chosen application field and
  concise labels are documented transformations.

## Technical research used for policy interpretation

The real-catalog Role 3 example uses a short attributed finding from
[Google Research's DS-STAR report](https://research.google/blog/ds-star-a-state-of-the-art-versatile-data-science-agent/).
Its publication/retrieval dates, assistant review, conditional interpretations,
limitations and live receipt are linked in the
[Role 3 evidence handoff](ROLE_3_ONET_HANDOFF.md). No full report is redistributed;
publisher material retains its own rights. This is contextual research rather
than occupational demand data.

Official Power BI, Tableau, Python, Java, Docker and Kubernetes documentation
was read to compare task-specific software capabilities. Links and qualitative
findings are in [Person 1 evaluation](PERSON_1_EVALUATION.md). No product manual
is redistributed, no transfer percentages were measured, and no external model
or paid API is required by the importer or experiments.
