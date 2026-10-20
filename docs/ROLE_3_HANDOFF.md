# Role 3 handoff to Persons 4 and 5

Data Analyst integration is ready. It uses Person 1's existing role/task/skill IDs,
two real dated contextual citations, and explicitly hypothetical scenarios.
The source observations do not measure task automation or employment forecasts.

A separate [evidence-chain deliverable](ROLE_3_EVIDENCE_CHAIN.md) now connects a
third reviewed finding (from the same January report) to conditional Python/SQL
learning implications. Consume `get_evidence_chain_response()` from
`src.intelligence.impacts`; display its proposed status and assumptions.
It does not change the numerical scenario priorities below. New reviewed releases
can be added through the local source registry without changing fetcher code.

## Message for Person 4: Learning Planner

Consume `get_outlook("role:data_analyst", scenario_id).scenario.skill_priorities`
from `src.intelligence.outlook`. Scenario IDs are `baseline`,
`moderate_ai_change`, and `rapid_ai_change`.

Join `skill_id` to Person 2's actual missing-skill gaps, then use
`adjusted_priority` when prioritizing those gaps. Each item also includes
`baseline_priority` and `applied_adjustment`. These values do not establish
proficiency or a gap. Preserve the user's reviewed skills and fit score.

The proposed calculation follows the project specification:
`adjusted_priority = clamp(baseline_priority + adjustment, 0, 1)`.
It is **additive, not a multiplier**. Please coordinate this contract before
wiring your planner. Do not multiply baseline by adjusted priority or apply the
adjustment twice. Course validation, budgets and prerequisites remain yours.

| Skill ID | Baseline | Moderate hypothetical | Rapid hypothetical |
|---|---:|---:|---:|
| `skill:python` | 0.70 | 0.75 | 0.80 |
| `skill:sql` | 0.90 | 0.90 | 0.90 |
| `skill:statistics` | 0.80 | 0.90 | 1.00 |
| `skill:data_visualization` | 0.80 | 0.80 | 0.80 |
| `skill:communication` | 0.60 | 0.70 | 0.80 |

Adjustment sizes are authored assumptions. Switching to baseline restores the
original weights. This source refresh changes cited outlook content, not these
numerical assumptions. Synthetic scenarios currently cover Data Analyst only.

## Message for Person 5: Frontend and Integration

Import `get_outlook_response` from `src.intelligence.outlook` for a JSON-compatible
response, or `get_outlook` for its Pydantic model. The three sample responses are
in `data/demo/data_analyst_outlooks.json` and work offline.

Display:

- `baseline_label`, task interpretations and `evidence_status`.
- Task `signal_ids` joined to `signals`, then `source_id` joined to `sources`.
- Citation links, publication and retrieval dates, coverage and limitations.
- `catalog_synthetic=true` for the fixture in every mode; the baseline is not
  observed role-demand data.
- `scenario.synthetic=true`, the hypothetical label and assumptions for moderate
  and rapid modes. Baseline `scenario.synthetic=false` means no scenario
  adjustment; it does not override the catalog's synthetic flag.
- A scenario comparison based on skill priorities, not a job-loss percentage.

Use `get_refresh_status()` from `src.intelligence.feeds` for the latest refresh
attempt. Show its warning when status is `cached` or `unavailable`; a missing
status means no attempt is recorded. Run `refresh_evidence()` in a separate
explicit/background job, not on every outlook request. A recent fetch does not
mean a recent publication. No HTTP routes or scheduler are created by Role 3.

Translate service errors in your API: unknown role is `KeyError`; unknown or
unsupported scenario is `ValueError`. Other catalog roles currently return
insufficient evidence for baseline and reject Data Analyst-only scenarios.
Do not expose every internal validation exception as a user input error.

## Verify and limitations

```bash
python -m unittest discover -s tests -v
python -m src.intelligence.outlook
python -m src.intelligence.feeds
```

The final command needs internet access. Full details are in
[the Data Analyst guide](ROLE_3_DATA_ANALYST.md) and
[the evidence refresh guide](ROLE_3_EVIDENCE_REFRESH.md).

Scope: one Data Analyst example and one approved refresh URL. Evidence is
historical and contextual; task mappings are interpretations. New sources need
review. Deployment, routes, course planning, and broader task-specific evidence
are not implemented by this handoff. Shared schema changes still require team
coordination under the project's schema protocol.
