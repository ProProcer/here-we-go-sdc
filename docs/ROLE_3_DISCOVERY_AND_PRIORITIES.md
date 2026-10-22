# Scheduled source discovery, finding review and learning-priority policy

**Start with the [AI attention brief](../data/review/discovery/REVIEW_BRIEF.md).**
The [AI-first review stage](ROLE_3_AI_REVIEW.md) now reads unapproved articles,
checks retrieved evidence and summarizes the specific points needing your
attention. The manual commands below remain available for final decisions.

The daily GitHub Actions workflow runs at **01:00 UTC / 09:00 Malaysia time**.
It can also run manually or after changes to discovery configuration on `main`.
GitHub may delay scheduled jobs. Repository Actions must remain enabled, and
GitHub may disable schedules on inactive public repositories after 60 days.
See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## What runs automatically

1. Read the official Google Research and Microsoft Research RSS feeds in
   [`discovery_feeds.json`](../data/sources/discovery_feeds.json).
2. Select recent titles matching the configured AI/work/analysis keywords.
   Default lookback is 90 days. This is title filtering, not a comprehensive
   search engine or a judgment that a finding is correct.
3. Canonicalize and deduplicate publisher-scoped URLs. Preserve review decisions,
   earlier candidates and per-feed failure receipts across runs.
4. Queue new links for source review. Feed metadata is provisional until checked
   against the article; publisher reputation alone does not establish credibility.
5. When a source has been explicitly approved and `GEMINI_API_KEY` is configured
   in repository Secrets, extract up to three new reports per run. Every generated
   finding remains `pending_review`. Without a key, link discovery still works.
6. Upload the queue, receipt hashes and candidate findings as the
   **role3-discovery-state** artifact, retained for 90 days. The next run restores
   the most recent available artifact and falls back to the committed initial
   queue. Archive artifacts before expiry when keeping a longer review history.

The workflow has read-only repository permissions. It does not commit findings,
send messages, approve evidence or publish numerical adjustments. The local
Gemini key is stored as an encrypted repository secret; it is never committed.
Model calls can incur charges, bounded to three newly approved sources per run.
Feed polling uses no paid model. A repeated feed failure preserves the queue;
when every feed fails the workflow fails visibly. Per-item extraction failures
are recorded in `extraction_error` and retried on subsequent runs.

## Review a newly discovered source

Download the latest artifact from the
[Actions workflow](https://github.com/ProProcer/here-we-go-sdc/actions/workflows/role3-discovery.yml)
and extract it into `data/review/discovery/` to review scheduled results locally.
Alternatively `python -m src.intelligence.discovery run` performs a fresh local
poll. Local and scheduled queues share URL-based identities.

```bash
python -m src.intelligence.discovery list
python -m src.intelligence.discovery review --id DISCOVERY_ID --decision approve --reviewer "YOUR_NAME" --reason "Original study; publication date, methods, scope and limitations checked."
```

Before approving, inspect the original article and methodology: identify the
publisher/authors, dates, study design, population, geography, sample limitations,
financial interests and whether the article is reporting original research.
Separate measured usage, surveys, labor-market observations, benchmarks and
forecasts. Reject unsupported publicity or irrelevant findings with
`--decision reject` and an explanation. Check whether other articles repeat the
same underlying study; repetition is not independent corroboration.

Approval verifies that the exact URL remains inside the configured publisher's
article scope and that a dated, parseable report is available. It appends a
source entry to `data/sources/approved_sources.json` and an audit decision to
`data/sources/discovery_decisions.json`. It does not admit a finding. Reviewer
labels are self-declared audit labels, not authenticated signatures.
Commit and push these two files so the next scheduled run sees your decision.
Metadata conflicts require investigation and an explicit reviewed correction;
the command will not silently overwrite an earlier decision.

## Review and admit a finding

```bash
python -m src.intelligence.discovery run --extract
python -m src.intelligence.approval list --candidate-file CANDIDATE_FILE
python -m src.intelligence.approval prepare --candidate-file CANDIDATE_FILE --finding 1 --role role:onet_15_2051_01 --task task:onet_16150 --interpretation "YOUR_REVIEWED_CONTEXTUAL_INTERPRETATION_AND_LIMITS"
python -m src.intelligence.approval approve --plan PLAN_FILE --reviewer "YOUR_NAME" --expected-plan-sha256 PRINTED_HASH --approve
```

The source date and saved supporting passage must still match the live report.
Read the passage, not just the generated paraphrase; correct the evidence type,
claim or limitations using the existing preparation options if necessary.
Include a real role/task mapping to admit the finding to the **real** ledger.
Without that mapping, the legacy CLI selects its mock ledger. Reject a finding
by leaving it unapproved; pending history is immutable and is never displayed as
accepted evidence. See [the finding review guide](ROLE_3_APPROVAL.md) for details.

An admitted contextual interpretation still does not authorize numerical skill
changes. The source, population and task may be relevant while the skill-specific
implication remains unsupported.

## Numerical learning-priority policy v1

Policy parameters are in
[`learning_priority_policy.json`](../data/sources/learning_priority_policy.json).
They are **conservative application assumptions**, not fitted coefficients,
confidence probabilities or measured predictions. Changing the policy invalidates
existing assessments until they are reviewed again.

The baseline occupational weight stays **O*NET Importance / 5**. Personal fit and
the occupation catalog are never rewritten by discovery or this policy.
The overlay affects learning priorities for existing general role-skill gaps.

Each proposed role/task/skill assessment must cite an explicitly approved **and
admitted** finding. A reviewer separately records a skill direction, rationale,
methodological quality, directness and underlying study identity. This is an
explicit reviewed inference; it does not claim O*NET supplied a task-skill edge.

| Parameter | v1 rule |
|---|---|
| Independent support | At least 2 eligible underlying studies and 2 publishers |
| Duplicate study | One contribution per `study_group`, regardless of the number of links |
| Publisher concentration | At most one contribution per publisher |
| Labor-market observation factor | 1.00 |
| Adoption survey factor | 0.75 |
| Observed usage factor | 0.50 |
| Benchmark, author projection or other | 0; contextual discussion only |
| Quality | Strong = 1; moderate = 0.5 |
| Relevance | Direct reviewed role/skill relevance required; indirect = excluded |
| Age | 180-day half-life from publication; exclude future or over-730-day evidence |
| Conflict | Withhold if the smaller opposing weight is at least 25% of the larger |
| Maximum evidence adjustment | ±0.10 on the 0–1 priority scale |

Use **strong** only when methods, sample and measurement are clearly described,
the outcome supports the proposed learning emphasis, and material limitations
are addressed in the rationale. Use **moderate** for usable but limited methods
or samples. Leave unsupported claims unapproved. Directness requires an explicit
connection to the selected role and skill; a generic AI capability demonstration
is indirect. Record geography limitations: U.S. occupational ratings and vendor
usage do not establish Malaysian demand. Independence, directness and semantic
support need human judgment; code cannot prove them from labels.

For eligible, deduplicated evidence:

```text
weight_i = evidence_type_factor × quality_factor × 2^(-age_days / 180)
P = sum(weights supporting increased learning emphasis)
N = sum(weights supporting decreased learning emphasis)

delta = 0.10 × (P - N)/(P + N) × min(1, (P + N)/2)
```

The support and conflict gates run before this calculation. Withheld or stale
assessments contribute zero. Two fresh, strong, independent labor-market findings
in the same direction reach ±0.10; two fresh observed-usage findings reach ±0.05.
Those are policy examples, not real results. Older evidence has less influence.
Conflicting interpretations within the same study group are excluded.

```text
learning_priority = clamp(O*NET baseline + authored scenario delta + evidence delta, 0, 1)
```

The existing moderate/rapid adjustments remain hypothetical assumptions and are
reported separately. `applied_adjustment` is the total effective change from the
original baseline, including clipping; consumers must not apply it a second time.

## Prepare, approve and inspect a skill assessment

```bash
python -m src.intelligence.priorities prepare --review APPROVED_DEFINITION --role role:onet_15_2051_01 --task task:onet_16150 --skill skill:onet_2_a_2_a --direction increase --study-group UNIQUE_UNDERLYING_STUDY_ID --quality moderate --relevance direct --rationale "YOUR_REVIEWED_ROLE_SKILL_CONNECTION_METHODS_AND_LIMITS"
python -m src.intelligence.priorities approve --plan PRINTED_PLAN --reviewer "YOUR_NAME" --expected-sha256 PRINTED_HASH --approve
python -m src.intelligence.priorities preview --role role:onet_15_2051_01
```

Preparation alone writes a review plan. Explicit approval checks the exact plan
hash, accepted finding, source fingerprint, evidence type, role/task references,
skill membership and policy version. Approvals are stored in
`data/processed/onet/31.0/priority_assessments.json`; commit approved definitions,
accepted evidence and assessments together. Withdraw an assessment by removing
its entry in an explicit reviewed repository change; history remains in Git.

`get_outlook()` evaluates the approved store offline on each call, with age decay.
Its real-catalog response includes `learning_priority_evidence`: policy version,
decision status, contributing/excluded assessment IDs, scenario contribution,
effective evidence adjustment and rejected/stale assessments. Person 5 should
display these explanations. Person 4 already consumes the adjusted priorities.
Tests cover this path into actual learning plans while preserving fit scores.

The current approved assessment store is intentionally empty: the existing single
DS-STAR benchmark supports contextual interpretations, not numerical weights.
No artificial corroboration or approval was manufactured to demonstrate a change.

## Verification

On 2026-10-22, both configured feeds were fetched successfully and seven links
were queued without admitting findings. All **177 unit/integration tests passed**,
including review isolation, failed fetch preservation, URL/date filtering,
duplicate studies/publishers, conflict and age handling, exact approval checks,
and end-to-end adjustment propagation into planning without changing fit.
Ruff checks and YAML parsing passed. The workflow's first hosted run is triggered
by its push to `main`; its result is available on the Actions page linked above.
