# Proposed task and skill implications from accepted findings

This stage consumes one explicitly approved **and admitted** finding plus a
selected role's existing tasks and skill requirements. Gemini proposes qualitative
interpretations or explains why the evidence is insufficient. Results are stored
separately for review; the stage does not publish them into the outlook or change
numeric weights.

## Run

Set `GEMINI_API_KEY` in your environment as described in
[the extraction guide](ROLE_3_EXTRACTION.md). The same model setting applies:
`GEMINI_MODEL`, or `--model`, defaults to `gemini-3.5-flash-lite`.

```powershell
python -m src.intelligence.proposals generate --review data/sources/approved_candidates/approved_88706a14b2cdd79b2546b84b_e601e6fc7679.json --role role:data_analyst
```

The command returns the saved proposal path, task count, assessment and
`status=pending_review`. Outputs are versioned under
`data/review/task_skill_proposals/`. The original candidate, accepted finding,
catalog, fit scores and scenario weights are not written by this operation.

To inspect exactly what would be sent to Gemini without a key or model call:

```powershell
python -m src.intelligence.proposals inspect --review data/sources/approved_candidates/approved_88706a14b2cdd79b2546b84b_e601e6fc7679.json --role role:data_analyst
```

For the generated live example, verify that its approved inputs and current
catalog still match:

```powershell
python -m src.intelligence.proposals check --proposal data/review/task_skill_proposals/data_analyst_approved_b230ffe9f9800a69f876ae15_93f0577e74e0.json
```

`check` runs offline. Its `current` status means the local accepted inputs,
catalog and prompt policy match; it does not verify the current report webpage,
discover newer research, approve the proposal or establish that its reasoning
is correct. The source's publication date remains historical even after a new
generation run.

## What the model can propose

Each supplied task must appear exactly once, with a reason connecting it to the
finding or explaining the missing evidence. A conditional interpretation needs
an explicit workflow change, adoption assumptions, remaining human
responsibilities and limitations. Its skill directions mean:

| Direction | Meaning |
|---|---|
| `increase` | More learning emphasis on specified aspects within the assumed workflow |
| `decrease` | Less emphasis on specified aspects within the assumed workflow |
| `mixed` | Different aspects move in different directions |
| `unchanged` | A proposed interpretation supports retaining emphasis, with rationale |
| `insufficient_evidence` | The finding does not support a direction |

Directions concern particular uses of a skill, not employer hiring demand or the
overall importance of knowing that skill. Every employer-demand direction stays
`insufficient_evidence`. No numerical priorities, confidence scores or job-loss
probabilities are requested or permitted by the output schema.

For an unsupported task, the model must return `task_change=null`, empty
assumptions/responsibilities, and insufficient evidence for every allowed skill.
This prevents an insufficient assessment from carrying a contradictory workflow
or skill increase in other fields.

## Catalog scope

Allowed skills are the intersection of the task's taxonomy links and the selected
role's existing skill requirements. The program validates exact coverage,
rejecting invented IDs, duplicate/omitted tasks, duplicate/omitted skills and
known skills assigned to the wrong task or role.

For the current Data Analyst fixture:

- Data cleaning: Python and SQL.
- Routine reporting: Data visualization. Spreadsheets appears in the task
  taxonomy but is not a Data Analyst requirement, so this stage does not add it.
- Statistics and Communication: role requirements without task links in this
  fixture. They are reported separately as `unmapped_role_skills` with insufficient
  evidence, rather than assigned invented links. This is a catalog coverage
  limitation, not evidence that those skills lack value.

`catalog_synthetic=true` remains visible. The model cannot turn the synthetic
catalog into measured job-market requirements.

## Admission and provenance checks

The selected definition must carry explicit finding approval provenance, pass
the source registry and approved-definition checks, and match a signal/source in
the accepted ledger. A candidate file or a reviewed definition whose refresh
failed cannot substitute for an admitted finding.

Only the accepted claim, reviewed evidence type, study period, limitations,
source metadata and selected catalog subset are sent to Gemini. The payload
omits reviewer identity, local file paths and numerical baseline weights. It is
treated as untrusted data, with no model tools or writer access.

The saved record includes the source citation, approved finding/audit, model and
prompt version, plus fingerprints of the definition, accepted input, catalog and
model payload. Inputs are rechecked after generation before the sole output write.
Failed calls or validation do not replace previous proposals.

Later checks detect changed approved wording, source metadata, definition file,
catalog or prompt policy. Unrelated new signals do not invalidate a proposal.
Updating only the source retrieval date does not change its evidential meaning.
Raw extraction/report text is not re-fetched or sent by this stage.

## Live example and review notes

The successful current live example is
`data/review/task_skill_proposals/data_analyst_approved_b230ffe9f9800a69f876ae15_93f0577e74e0.json`.
It returns **insufficient evidence** for both Data Analyst tasks and all three
linked skills: an aggregate platform collaboration finding does not establish
task-specific adoption or skill changes. That is a useful supported outcome.

An earlier live output, ending in `_1401e5363916.json`, is retained as history.
It proposed conditional workflows but overreached when suggesting that aggregate
platform use establishes frequent reporting assistance. It was never approved
or published. Prompt policy v2 explicitly rejects assuming the missing
task-specific connection; `check` rejects that older-policy output as stale.

These examples are integration tests, not an extraction or reasoning accuracy
benchmark. Schema and scope checks cannot prove semantic support. A reviewer
must still inspect the connection, assumptions and any causal wording. New
AI-generated task/skill proposal approval/publication is a separate step; the
existing `impacts` command continues to read its established evidence chains.

## Implementation and tests

| Module | Responsibility |
|---|---|
| `src/schemas/proposals.py` | Strict qualitative proposal and review-record contracts |
| `src/intelligence/proposals.py` | Accepted-input checks, catalog scope, validation, persistence and CLI |
| `src/intelligence/proposers.py` | Provider interface, Gemini instructions and input-specific response bounds |
| `src/intelligence/gemini.py` | Shared typed JSON client reused by extraction and proposals |

The provider schema is narrowed to the role's actual task/skill counts; full
Pydantic and domain validation still run locally. Scalar Literal values are
represented as typed enums for Gemini compatibility, including older Pydantic
schema output. The existing report extractor retains its public interface.

```bash
python -m unittest discover -s tests -v
```

Tests cover accepted-input gates, conditional and insufficient results, scope,
extra numeric/approval fields, consistent skill aspects, input changes, provider
failures, history, payload privacy, schema bounds and stale proposal checks.
Normal tests use fictional temporary evidence and a stub provider; no API key
or network access is needed. The historical evidence-chain demo test now checks
its saved snapshot rather than assuming today's accepted ledger never changes.

Provider reference: [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
