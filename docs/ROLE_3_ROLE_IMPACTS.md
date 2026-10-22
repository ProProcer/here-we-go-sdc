# Role-specific evidence checks

The daily pipeline now runs:

**Discover news → shared source checks → skill checks → role shortlist → role/task
checks → human decisions.** Source checks and skill suggestions may run before
source approval. Role checks start only after the source is approved.

## What the AI checks

Successful positive skill checks shortlist catalog roles containing those skills,
including software associations. A skill check does not need human approval to
create a candidate, but rejected, failed, challenged, negative or insufficient
checks do not enter the shortlist. Skill membership is a search aid, not proof
of occupational impact. Broad general skills can shortlist many roles.

For each candidate, Gemini reads the role description, actual catalog task
statements and the article's stored grounded findings. A separate skeptic pass
checks the interpretation. A positive result must cite available findings and
specific tasks, state applicability conditions and list remaining human checks.
Invalid, duplicate or invented article/task/finding references are rejected.
Missing task statements produce cached insufficient evidence without an AI call.
The O*NET task-to-skill links remain unmapped: this feature does not invent them.

The result is **conditional role/task relevance**, not proof of changed employment,
wages, skill demand or numeric learning priorities. Selected findings are not a
complete article archive, and an empty shortlist does not prove a role is unaffected.

## Your menu

1. Open **Review Role 3.cmd** and click **Load latest GitHub report**.
2. Review and approve sources in **Sources**; save decisions to GitHub so the
   workflow can use them. Your laptop does not need to remain on.
3. Review skill suggestions in **Skill connections** and reject unsupported links.
4. After a daily or manual workflow run completes, load its report and open
   **Role impacts**. Read the specific task, finding/quote, conditions and skeptic
   concerns. Approve or reject each proposed role impact separately.
5. **Ask AI to check again** targets only that role/article pair and preserves its
   previous records. A failed recheck is clearly blocked locally; retry it before
   approving. Rechecks never approve results themselves.
6. **Save to GitHub** publishes decisions and their exact role, skill and source
   provenance. Rejection requires a note. Revised decisions keep their history.

The same status filters apply: **Needs review**, **Approved**, **Rejected**,
**No connection found**, **Insufficient evidence**, **Check flagged**, **Check
failed**, and **All**. Role shortlist counts show checked versus candidate pairs;
skill backlog remains visible. All 910 roles are not automatically declared checked.
New results arrive gradually because both stages have bounded budgets.

## Scheduling and cache

The existing 09:00 MYT GitHub Actions workflow includes up to three role batches
per run, each covering one role against up to eight articles. Each eligible batch
uses a draft and skeptic call with the existing bounded model fallback policy.
The workflow allows 40 minutes and saves state even after a failed step.

The cache binds the role title, description, task statements, skill definitions
and memberships, selected findings, supporting skill assessments, prompt version
and requested model. Unchanged pairs are reused. New roles enter the shortlist
using existing skills; changed roles or evidence invalidate affected results.
Rejected/withdrawn sources and rejected or failed supporting skill checks cannot
keep an active approved role impact. Removed roles disappear from active lookups;
their historical records remain auditable.

This is coverage of shortlisted roles only. Unchecked skill/article pairs can
still reveal additional candidates; no role in the missing shortlist is assumed
unaffected. There is no automatic bulk approval.

## Storage and team integration

- Decisions: `data/sources/role_evidence_decisions.json`, committed when saved.
- Immutable records: `data/review/discovery/role_assessments/<sha256>.json` in
  workflow artifacts; decided or locally rechecked records are published by Save.
- Summary: `ROLE_REVIEW_BRIEF.md` in the workflow summary and state artifact.
- Retry state: `role_jobs.json` in the artifact; gitignored in local checkouts.
- Local downloaded state: `.role3-review/`, gitignored.

Daily artifacts retain the existing **90-day** retention. Saved decisions and
their supporting records remain in Git history. No API key, credential or local
session file is included. Reviewer identity and notes are not sent to Gemini.

Other team members can call `CareerBackend.role_impacts(role_id)` to read approved,
current conditional role impacts offline, including cited tasks and supporting
findings. This does not invoke AI or modify existing outlook scores, role matching
or learning weights. `CareerBackend.skill_evidence(role_id)` remains available for
the separate shared skill interpretations.

```powershell
uv run --no-project --python 3.12 --with pydantic==2.12.3 python -m src.intelligence.role_evidence plan
uv run --no-project --python 3.12 --with pydantic==2.12.3 python -m src.intelligence.role_evidence run --max-batches 3
uv run --no-project --python 3.12 --with pydantic==2.12.3 python -m src.intelligence.role_evidence role --id role:onet_15_2051_00
```

The `run` command needs a Gemini key in the environment. `plan` and `role` are
read-only and require no model access. For an intentional targeted reassessment,
use `run --role <canonical-role-id> --force`; the menu additionally limits it to
the selected article. Review and save human decisions through the menu.

## Verification

On 2026-10-23, **254 tests passed**, including role shortlisting, task/finding
validation, cache reuse, changed contexts, explicit approvals, failed rechecks,
decision history and publishing the full source/skill/role provenance chain.
The native role tab and review controls passed layout checks at 940×680 and
1180×820. All 910 catalog roles loaded; the existing local report had no eligible
positive skill checks, so its zero role candidates were correctly shown as an
empty shortlist with upstream work still pending.

A small live Gemini probe using only fictional fixtures completed both passes
(draft: `gemini-3.5-flash-lite`; skeptic: `gemini-3.1-flash-lite`) and produced one
pending human review. No real source, skill or role decision was made during
verification. Changed Python files passed Ruff and the changed-file credential scan.
