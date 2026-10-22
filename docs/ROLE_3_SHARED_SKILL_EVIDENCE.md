# Expandable shared skill evidence

The default source reviewer now reviews work/learning evidence independently of
any occupation or skill catalog. A separate stage assesses each skill against
stored, supported findings. End-user role queries only join saved results with
Person 1's current role–skill catalog; they never call Gemini or refetch news.

## What changes trigger work

| Catalog or evidence change | Work required |
|---|---|
| Add a role using existing skills | Reuse stored skill assessments; no AI call |
| Change a role's title, tasks or skill memberships | Read current memberships; occupational/task applicability remains a separate review |
| Add a skill | Assess only this skill against every stored shared-reviewed article |
| Change a skill definition, label, aliases or kind | Reassess only this skill; previous approvals become inactive |
| Add or change an article's reviewed findings/text | Assess only this article against current skills |
| Remove a skill | Hide its assessments; preserve history |
| Reintroduce the identical skill | Reuse matching assessments if source/model/prompt versions still match |
| Change the mapping prompt or model | Queue new assessments; older ones remain historical |

Keys use canonical skill definitions and source-evidence versions, not a whole
catalog hash, role ID, catalog release label or catalog list order. Both negative
and insufficient-evidence decisions are cached. A skill ID rename is a new skill
unless Person 1 supplies an explicit migration; the AI does not silently merge IDs.
Import Person 1's validated updated catalog before running the job. The scheduled
runner starts a fresh process and reads the latest checked-out catalog. A persistent
application must reload its catalog/backend after an import.

## Stored coverage and the initial migration

The old reviews were BI-specific. They remain in history and are counted as
**awaiting shared review**, never treated as proof that another skill is irrelevant.
The next scheduled source-review batches replace the active references with shared
reviews, without approving any source or finding.

Stored news currently means source metadata, content hashes, selected supported
findings, short exact quotes, quality checks and limitations. It does **not** mean
a complete offline copy of every article. Shared review selects at most two
findings, so assessment covers those findings, not every statement in the article.
Missing support is reported as insufficient evidence where coverage is inadequate.
An article without grounded findings receives an explicit insufficient-evidence
record without an AI mapping call. Failed source refreshes and metadata conflicts
are excluded until resolved; the report exposes the missing coverage.

This design backfills every stored shared-reviewed article for a new skill; it
does not rediscover news or repeat source verification just because a skill changed.
Source freshness checks still run separately on the existing seven-day cadence,
and source approval refetches the article to detect changed text.

The initial O*NET catalog contains **8,687 skill entries**, including 35 general
skills and many named software examples. Full initial mapping is a substantial
backfill. The default daily limit is three batches, each covering one skill and
up to eight articles, with at most two Gemini calls per batch. General skills go
first during the initial import; new/changed definitions and unattempted jobs
are prioritised, with fair retries after failures. Every report shows completed
pairs, pending pairs and articles awaiting shared review. It must not be described
as complete until those counts reach zero. Batch limits control cost; an explicit
`--skill` run can prioritise a newly introduced skill immediately.

## Review and approval

The latest Actions run Summary contains both the source attention brief and
`SKILL_REVIEW_BRIEF.md`; the `role3-discovery-state` artifact includes the records.
The committed briefs are snapshots, not the latest daily run.

Each skill/article assessment proposes potential relevance, no relevance, or
insufficient evidence. Positive mappings must cite available supported finding
indices and give applicability conditions. A separate skeptic call challenges
the whole interpretation. Missing/duplicate article verdicts and invented finding
references are rejected mechanically. A rejected challenge remains flagged for a
human rather than becoming an approved mapping. Two model calls are not independent
empirical corroboration.

Your brief highlights positive and uncertain mappings, their conditions, supporting
findings and remaining questions. Cached negative judgments stay in the artifact.
The summary shows at most 50 mappings, prioritising unresolved checks and pending
decisions; all immutable records remain available in the artifact.
Source approval remains separate. After approving the source and reviewing a
proposed conditional mapping, use its exact canonical SHA-256 from the brief:

```bash
python -m src.intelligence.skill_evidence approve --expected-sha256 MAPPING_HASH --reviewer "Ivan" --approve
```

This signs conditional skill relevance only. Commit the resulting
`data/sources/skill_evidence_decisions.json` and the referenced immutable assessment
and source-review records so downstream readers can reproduce the approval.
The workflow restores assessment history from artifacts; approval decisions come
from the checked-out repository, not a restored artifact.

Approvals are active only while the current skill/evidence/model/prompt key matches,
the source remains approved, no retrieved correction notice is present, and the
mapping passed its challenge. A change hides the old mapping until a new review.
No AI model can approve a mapping. Approving it does not admit a numerical priority
assessment or establish a measured occupational effect.

## Local use and integration

```bash
python -m src.intelligence.source_review run --max-reviews 3
python -m src.intelligence.skill_evidence plan
python -m src.intelligence.skill_evidence run --max-batches 3
python -m src.intelligence.skill_evidence run --skill skill:onet_2_b_3_e --max-batches 20
python -m src.intelligence.skill_evidence show
python -m src.intelligence.skill_evidence role --id role:onet_15_2051_01
```

Use actual current catalog skill IDs; the focused command can be repeated until
that skill's backlog completes. `plan`, `show`, and `role` require no API key or
network. AI runs use the existing `GEMINI_API_KEY` and `GEMINI_MODEL` configuration.
To resolve a disputed or flagged interpretation, add `--force` with explicit
`--skill` IDs. This preserves history and replaces the active assessment with the
newest successful review. Existing approvals do not transfer to a new assessment.
Default scheduling remains 09:00 MYT. A catalog-file push also triggers the workflow.
The old `ROLE3_REVIEW_ROLE` variable is no longer used by the scheduled job;
`source_review run --role ROLE_ID` remains available for an explicit legacy review.

Persons 2–5 can use `CareerBackend.skill_evidence(role_id)` or
`evidence_for_role(role_id, catalog=updated_catalog, state_path=downloaded_queue)`.
The return value contains approved conditional skill evidence, pending review
counts and coverage gaps. It uses both general requirements and software
associations, preserving their different meanings. Software group membership
does not imply tool equivalence.

Role membership identifies potential relevance. The stored conditions must still
fit actual work before anyone asserts a role/task impact. Imported O*NET task–skill
links remain unmapped. This reader does not write to the accepted evidence ledger,
modify catalog weights, alter personal fit, or bypass the existing separately
approved independent-evidence policy for numerical learning-priority changes.

Tests cover incremental catalog changes, source changes, negative caching,
backlog limits, failed retries, legacy review exclusion, exact coverage,
unsupported references, skeptic vetoes, approval invalidation and offline role
reuse. No source, finding or mapping was human-approved by these tests or AI runs.

Verification on 2026-10-22: **208 tests passed**, changed Python files passed Ruff,
and workflow schedule/permissions, JSON and changed-file credential checks passed.
The seven existing articles received shared source reviews after transient Gemini
503 errors were retried. A focused live Programming run produced a conditional
mapping and cached negative results; its initial overbroad interpretations were
blocked by the skeptic and retained only as historical records. Initial mapping
of the remaining catalog entries is still a visible, budget-capped backlog.
