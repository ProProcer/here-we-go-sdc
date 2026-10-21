# Person 1 evaluation and decision evidence

These results use the pinned O*NET® 31.0 CSV snapshot. They test catalog
integrity and an exploratory coverage policy; they do not measure employment
prediction, real proficiency or the effectiveness of courses.

## Coverage audit

`python -m src.ingestion.onet` reproduces the following:

| Measure | Actual result |
|---|---:|
| Original occupation records | 1,016 |
| Included occupations | 910 (89.57%) |
| Excluded occupations | 106 (10.43%) |
| Missing both tasks and all skill/software detail | 93 |
| Additional occupations missing general skill ratings | 13 |
| General role-skill pairs before relevance selection | 31,850 |
| Irrelevant pairs omitted | 3,515 |
| Retained general requirements | 28,335 |
| Suppressed Level values withheld among retained pairs | 146 |
| Imported task statements | 18,592 |
| Software observations | 31,194 |
| Software categories | 134 |
| Occupations with no In Demand software examples | 423 |

The exclusion audit lists every source code, title and reason. The 93 occupations
without detailed data comprise 74 catch-all nonmilitary occupations and 19
military occupations. The importer treats exclusions as missing source coverage,
not evidence that a career is unsuitable.

## Why flat software counts should not determine score influence

Across the 910 occupations:

| Per occupation | Minimum | Median | Maximum |
|---|---:|---:|---:|
| Relevant general skills | 19 | 31 | 35 |
| Software observations | 1 | 21 | 430 |
| In Demand software examples | 0 | 1 | 38 |

Giving every software example weight 1 and pooling it with normalized general
importance would assign software **5.60% to 95.75%** of the total weight, with a
median of **54.29%**. That follows from source list length, not a reviewed claim
about the occupation's needs. Separate component normalization avoids that
accidental weighting.

## Six-occupation semantic sample

This purposive sample illustrates contrasting roles. It is not a random sample
and does not establish population transfer rates.

| Occupation | General count | Software count | In Demand count |
|---|---:|---:|---:|
| Business Intelligence Analysts | 30 | 203 | 14 |
| Software Developers | 33 | 430 | 30 |
| Accountants and Auditors | 27 | 237 | 6 |
| Registered Nurses | 32 | 43 | 0 |
| Electricians | 34 | 30 | 0 |
| Customer Service Representatives | 27 | 112 | 3 |

General skills include Programming, Repairing and Troubleshooting as well as
Reading Comprehension and Social Perceptiveness. They are not exclusively
soft skills. Software names are specific technologies; claims about them may
overlap with general capabilities and need careful explanation.

## Task-context review

Official product documentation was inspected to assess the meaning of candidate
alternatives. These are qualitative analyst judgments, not accepted transfer
percentages or a reviewed task-skill mapping in the imported catalog.

| Candidate relationship | Shared preparation | Remaining gap |
|---|---|---|
| Tableau to Power BI for a new report | Visualization and report design concepts | Target interface, modeling and calculations |
| Tableau to maintaining DAX in an existing Power BI model | Analytical concepts | Specific DAX/model implementation knowledge |
| Python to Java development | Some programming/class concepts | Language, types, libraries and tooling |
| Docker to Kubernetes operations | Container concepts | Cluster/workload orchestration; these tools are complementary rather than interchangeable |

Sources: [Tableau dashboard documentation](https://help.tableau.com/current/pro/desktop/en-us/dashboards_create.htm),
[Power BI report tutorial](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-dimensional-model-report),
[Power BI modeling and DAX](https://learn.microsoft.com/en-us/training/paths/model-power-bi/),
[Python tutorial](https://docs.python.org/3/tutorial/index.html),
[Java introduction](https://dev.java/learn/first-steps/first-java-code/),
[Docker overview](https://docs.docker.com/get-started/docker-overview/),
[Kubernetes overview](https://kubernetes.io/docs/concepts/overview/).

Conclusion: retain exact identities and award only explicitly labeled category
familiarity at the broad source-category level. Do not automatically declare
category members interchangeable or generate accepted task-to-skill edges.

## Sensitivity experiment and policy choice

`python -m src.ingestion.onet_experiments` tests a 3×3 grid:

- General share: 0.25, 0.50, 0.75.
- Software category share: 0.25, 0.50, 0.75.
- For each sampled role: general-only, software-only, and alternating-half
  synthetic profiles, for **162 score evaluations**.

General-only/software-only examples in roles with demand signals can move by
50 points across the general-share range. Mixed examples in the four roles
with demand signals move by 0.84–7.68 points. Roles without demand signals
remain unaffected by either software weighting parameter.

The data therefore do not identify an objectively optimal ratio. Equal shares
are selected as explicit, editable provisional defaults because the available
data provide no calibrated cross-domain tradeoff. The earlier suggested 70/30
ratio is not adopted as an evidence-based result. Independent reviewers and
representative fictional profiles are needed before claiming a calibrated fit
policy. Those future reviews are not prerequisites for the catalog handoff.

## Structural experiments actually executed

The committed experiment report records:

- Empty/full profile score boundaries for **910 occupations**.
- **59,529** incremental skill additions without decreasing coverage.
- Missing-software reweighting checks for **423 occupations**.
- A category example verifying Java does not award an exact Python match.

These checks establish deterministic bounded behavior under the stated policy,
not predictive validity. All software examples remain optional occupational
observations; even a full score does not verify qualifications or licensing.

## Regression and integration tests

The original baseline suite passed **136 tests** before changes.
`tests/test_onet_catalog.py` adds **13 tests** covering source integrity,
rebuild determinism, known counts, relevance, suppressed levels, unmapped tasks,
stable/unique aliases, rejected bad references, missing software, exact/group
credit, reviewed profile intake, bounded policies and paged/detail adapters.

Full verification: **149 tests passed**, including the original 136 and the
13 new catalog tests, using Python 3.12 with Pydantic 2.12.3 and pypdf 6.21.1.
The importer, experiment command and demo command also completed successfully.
No tests are live API, hiring accuracy, user study, or course-success tests.

## Practical limits

- O*NET describes U.S. occupations, not confirmed Malaysian current demand.
- Some records predate the release; release date is not observation date.
- There is no imported task-skill crosswalk, qualification gate, or Level calibration.
- Category familiarity is coarser than task-specific alternatives.
- Broad occupations can combine several employer technology stacks.
- Full teammate adoption requires the coordinated changes in the migration guide.
