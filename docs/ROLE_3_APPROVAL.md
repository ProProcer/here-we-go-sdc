# Approve a candidate without hand-editing JSON

The approval CLI turns one extracted candidate into a reviewed source definition
and admits it through the existing evidence refresh pipeline. It does not call
Gemini, require an API key or generate a job/skill interpretation.

## Review and prepare

List the findings in your extraction file:

```powershell
python -m src.intelligence.approval list --candidate-file data/review/candidates/anthropic_economic_index_2026_01_20261020T153412230377Z_1f9402f1d467.json
```

After checking the source, prepare a plan for one finding:

```powershell
python -m src.intelligence.approval prepare --candidate-file data/review/candidates/anthropic_economic_index_2026_01_20261020T153412230377Z_1f9402f1d467.json --finding 1
```

This step is offline. It saves a `prepared` plan under `data/review/approvals/`
and prints the path, SHA-256 and full contents. It changes neither the candidate
nor the accepted ledger. You can use `--candidate-id` instead of a finding number.

The first finding from that actual file has already been prepared as:

`data/review/approvals/plan_b230ffe9f9800a69f876ae15_1e9198c8c08b.json`

It contains no task mapping. Ivan approved this finding on October 20, 2026;
its admitted definition is
`data/sources/approved_candidates/approved_88706a14b2cdd79b2546b84b_e601e6fc7679.json`.
Preparing a plan alone is not approval or admission.

## Apply corrections

You can supply reviewed corrections when preparing a new plan:

- `--claim "Corrected original paraphrase"`
- `--limitation "Corrected source limitation"` (repeat to supply multiple items;
  supplying this option replaces the candidate's generated limitations)
- `--evidence-type author_projection` (corrects the generated classification)

For example, the third finding in this extraction file concerns an economic
projection but Gemini labeled it `benchmark`. Review the report and use
`--evidence-type author_projection` if accepting that finding. The audit retains
both the original extracted type and the reviewed type. A projection is labeled
as such in the accepted signal, rather than presented as an observed outcome.

## Approve the prepared plan

For the existing first-finding plan:

```powershell
python -m src.intelligence.approval approve --plan data/review/approvals/plan_b230ffe9f9800a69f876ae15_1e9198c8c08b.json --reviewer "Ivan" --approve
```

Use your actual reviewer name. `--approve` is required and records your explicit
decision about the plan's current wording, limitations, classification and any
task mapping. Reviewer names are locally supplied audit labels, not authenticated
identities or cryptographic signatures.

For an exact file binding, also pass the `--expected-plan-sha256` printed by
`prepare`. A different hash blocks admission before fetching the source. Candidate
file changes after preparation always require a new plan.

Approval then:

1. Checks the plan, immutable candidate file hash, candidate content ID, source
   registry metadata and any role/task mapping.
2. Fetches the report once, parses it and compares the readable-text hash with
   the extraction. HTML-only changes such as comments do not invalidate it.
3. Rechecks the saved quote, offsets, paragraph hash and study-date references.
4. Generates a reviewed source definition under `data/sources/approved_candidates/`.
5. Passes the already fetched bytes through the normal refresh validation and
   atomic ledger replacement. A source snapshot stores the approval provenance.

Success returns `status=approved`, the reviewed source path, refresh status and
snapshot path. Repeating an identical approval does not duplicate a signal.
An existing candidate signal with different accepted wording is rejected rather
than silently overwritten. That case needs a deliberate revision workflow; it is
not implemented by this command.

The extraction file retains `pending_review` as immutable extraction history.
The reviewed definition and snapshot record the separate approval decision,
reviewer, time, file hashes, supporting passage, dates, limitations, model and
original/reviewed evidence classifications. This is the acceptance record.

## Optional role/task mapping

Approving a finding alone does not establish how a particular role is affected.
With no mapping, the finding is stored in the accepted ledger but is not added
to role-specific outlooks. Existing outlooks include only signals linked to their
tasks.

To separately approve an interpretation, supply all three options to `prepare`:

```powershell
--role role:data_analyst --task task:data_cleaning --interpretation "Your reviewed contextual interpretation and its limits."
```

The role/task pair must already exist in the catalog. The interpretation is
explicitly marked `team_interpretation` and `contextual_not_task_measurement`.
It enters the outlook when that plan is approved. The current merge retains
previous citations for the task and replaces its display interpretation with
the newly approved wording; inspect existing context before approving a mapping.

No skill weights, fit scores, role requirements or synthetic scenarios change.
This command does not create new task-to-skill reasoning chains. The separate
[task/skill proposal stage](ROLE_3_TASK_SKILL_PROPOSALS.md) is now available:
it consumes an admitted finding, generates review-only implications and supports
explicit insufficient-evidence outcomes. It does not automatically publish those
new implications.

## Refresh and failure behavior

The generated definition can be refreshed with:

```powershell
python -m src.intelligence.feeds --review PATH_TO_GENERATED_DEFINITION.json
```

Approval-generated definitions remain bound to the reviewed report text. If that
text changes, refresh preserves the prior accepted ledger and requests a new
extraction and review. A new report or release can be registered and extracted
normally; no retraining is needed. Original marker-based definitions retain their
existing refresh behavior.

Network errors, stale candidates/reports, invalid references and failed
pre-admission checks do not change the accepted ledger. A reviewed definition
can remain on disk if the subsequent refresh fails; it is not proof of ledger
admission. Inspect the returned refresh status. The definition, snapshot and
ledger are separate atomic writes, not one filesystem transaction; if a disk
error interrupts status recording, inspect the ledger and snapshots before retrying.
As with the existing feed pipeline, run one ledger writer at a time.

## Verification

```bash
python -m unittest discover -s tests -v
python -m scripts.smoke_finding_approval --candidate-file data/review/candidates/anthropic_economic_index_2026_01_20261020T153412230377Z_1f9402f1d467.json
```

Unit tests use fictional HTML, temporary candidates and temporary ledgers. They
cover explicit approval, corrections, optional mappings, audit snapshots, stale
files/source content, source references, deduplication, failed writes and legacy
evidence preservation.

The live smoke test fetches the real report but simulates admission only in a
temporary copy of the ledger. It performs no human review and approves nothing
for the application. The recorded run in `data/demo/finding_approval_smoke.json`
shows the temporary signal count increasing from 3 to 4 while the application
ledger SHA-256 remains unchanged.
