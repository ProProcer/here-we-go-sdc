# AI-first source review

The scheduled reviewer now uses a shared work/learning scope. See the
[expandable skill-evidence guide](ROLE_3_SHARED_SKILL_EVIDENCE.md) for incremental
catalog updates, skill mapping approval, coverage limits and the additional brief.
The occupation-specific behavior below remains available with `--role ROLE_ID`;
it describes the earlier BI seed batch rather than the current scheduled default.

Read the [attention brief](../data/review/discovery/REVIEW_BRIEF.md) first.
The AI reads articles before source approval and narrows the human workload to
specific uncertainties and decisions. It does not require you to read every
article before receiving a summary.

## Your daily workflow

Open the latest run of [Role 3 source discovery](https://github.com/ProProcer/here-we-go-sdc/actions/workflows/role3-discovery.yml).
Its **Summary** shows the attention brief; the `role3-discovery-state` artifact
contains the same Markdown and the evidence records.

The table groups articles as:

- **Ready for your decision:** role-relevant context passed the implemented
  checks; read the listed remaining questions before deciding to approve.
- **Check flagged points:** review the specific missing methods, interpretation,
  independence or source-content question identified by the AI.
- **Skip for this role:** the AI recommends spending no further time on this
  article for the selected occupation. This is a suggestion, not a recorded
  human rejection or a claim that the research is poor.
- **Awaiting AI review / refresh failed:** the run has not produced a valid new
  review. Failure is visible; an old review is labeled as old, never silently
  represented as a successful new check.

Expand an article's evidence notes only when needed. They contain a short
summary, grounded findings, quality checks with paragraph IDs, links to retrieved
study leads, access limitations and the specific questions requiring attention.
There is no numerical "credibility score" or automatic finding approval.

## What the AI and code check

1. **Fetch the real article.** Enforce the configured publisher/path scope,
   HTTPS, no credentials, no automatic redirects and bounded downloads. Verify
   the stated publication date appears in readable article text.
2. **Trace available original research.** Fetch at most one linked arXiv abstract
   or DOI's Crossref metadata. Only established arXiv/Crossref endpoints are
   permitted; arbitrary links suggested by the article or model are not fetched.
3. **Look for related research.** Query Crossref by article title, retrieve up
   to three metadata/abstract candidates, and filter weak title matches. The
   search may find no useful independent evidence; that remains an explicit gap.
4. **Produce a structured review.** Gemini checks authorship, methods,
   limitations and relevance to the actual O*NET occupation's tasks. It proposes
   at most two short findings with source paragraph IDs and exact short quotes.
5. **Validate references mechanically.** Reject invented passages and quotes.
   Correct an adjacent-paragraph locator only when its exact quote appears in
   exactly one paragraph of the same fetched article. Record every correction.
   Metadata-only matches cannot establish corroboration and are downgraded.
   An unmatched quote can still produce a clearly blocked attention item, but
   no finding from that review becomes eligible for acceptance.
6. **Challenge the draft.** A separate model call checks complete claims against
   the retrieved context, including missing qualifiers, numerical interpretation,
   benchmark/workplace confusion and unsupported role relevance. Only findings
   supported by this pass become pending extraction candidates.
   Mechanical grounding must also pass. Contradictory skip/relevance judgments
   are escalated for a human check even when the challenger overlooks them.
7. **Write your attention list.** Summaries and candidate findings remain in the
   review area. Neither model can write accepted evidence or learning priorities.

This adapts [SIFT's source investigation, comparison and tracing principles](https://hapgood.us/2019/05/12/sift-and-a-check-please-preview/)
and accounts for [NIST's warning that generated citations and reasoning can be erroneous](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf).
It is a practical review aid, not a certified implementation of an evidence
grading system. Exact-quote validation establishes text presence; semantic
support still relies on fallible AI judgments and your final decision.

The two passes may use the same configured Gemini model. A second pass is not
independent empirical evidence. Abstract-only retrieval cannot verify a full
paper's methods, result tables, peer-review status or experimental reproducibility.
A publisher blog and its linked paper are one study. No retrieved correction
notice does not establish absence of corrections or retractions. These limitations
are surfaced for review rather than converted into reassuring badges.

## Approve after checking the brief

Download the latest artifact into `data/review/discovery/` when working locally.
The article's evidence notes provide its review ID and review SHA-256.

```bash
python -m src.intelligence.source_review approve --id REVIEW_ID --expected-sha256 REVIEW_HASH --reviewer "Ivan" --approve
```

This binds your source approval to the exact AI review you inspected, rechecks
the current source text and catalog context, and rejects a changed article or
review. Your decision is recorded separately from the AI recommendation. It
approves the source only. For a rejection, the existing command remains:

```bash
python -m src.intelligence.discovery review --id REVIEW_ID --decision reject --reviewer "Ivan" --reason "YOUR_REVIEW_REASON"
```

Commit/push the source registry and source-decision files as described in the
[existing review guide](ROLE_3_DISCOVERY_AND_PRIORITIES.md). The AI review already
provides a grounded candidate file, so another extraction call is not required.
Use the existing finding approval CLI to check selected claims, prepare the real
role/task interpretation and admit the finding. A subsequent numerical skill
assessment still requires its separate approval and independent-evidence gates.

You can also ask the assistant to apply your decisions to specified review IDs;
the AI's recommendation alone is never treated as your approval.

## Run locally and control cost

```bash
python -m src.intelligence.discovery run
python -m src.intelligence.source_review run --max-reviews 3
python -m src.intelligence.source_review show
```

`GEMINI_API_KEY` is required for AI review. The default is now a shared work/learning
review; `--role` explicitly selects a legacy occupation-specific review.
`ROLE3_REVIEW_ROLE` is no longer used by the workflow. `--force` deliberately
bypasses the source-review cache.

The daily job attempts at most three reviews, with two model calls per successful
review, and preserves valid summaries for seven days. Model, prompt, role or
source-metadata changes invalidate the cache. Source text is fetched again at
human approval. Older immutable review files remain available, and restoration
of an older Actions queue can recover newer matching committed review files.
Failed attempts do not overwrite earlier reviews and are retried fairly on later
runs. A separate legacy extraction stage remains capped at three approved
sources. There are no hidden retries within an individual model request.

Only public report text, public study metadata and public occupation/task context
are sent to Gemini. Reviewer identity, private profiles, Git credentials and API
keys are not included in model input. Keys are sent only to their intended API
in authentication headers and never stored in briefs. Article text is not
redistributed: saved records contain short paraphrases/quotes, hashes, references,
model versions and explicitly pending candidates. JSON writes use LF across
platforms so review-file hashes survive Windows/GitHub checkouts.

## Verification

The live seed batch produced briefs for all seven discovered articles. For BI
Analysts, two were suggested for a decision, one was flagged for contradictory
scope assessments, and four were suggested skips. All recommendations remain
pending your decision. No source, finding or numerical priority was approved by
these AI runs. Tests cover citation/locator validation, a skeptical pass rejecting
overstatements, metadata-only downgrades, recommendation conflicts, safe URL
retrieval, cache restoration, failed refresh preservation, stale approval checks
and sanitized schema diagnostics.

Local verification on 2026-10-22: **193 tests passed**; changed Python files passed
Ruff, workflow YAML parsed successfully, the active briefs' review hashes and
pending-candidate contracts matched, and the changed-file secret scan passed.
