# Role 3: Data Analyst example

This integration example connects Person 1's existing IDs to a cited,
cached task outlook and deterministic hypothetical learning priorities.
It does not start a server or change the role catalog.

## Try it

From the repository root, with Python 3.10+ and the project dependencies installed:

```bash
python -m src.intelligence.outlook
python -m src.intelligence.feeds
python -m unittest discover -s tests -v
```

```python
from src.intelligence.outlook import get_outlook, get_outlook_response

baseline = get_outlook("role:data_analyst", "baseline")
rapid = get_outlook_response("role:data_analyst", "rapid_ai_change")
```

`get_outlook` returns a Pydantic `RoleOutlook`; `get_outlook_response` returns a
JSON-compatible dictionary. Person 5 can consume the three examples in
`data/demo/data_analyst_outlooks.json` immediately. The scenario comparison is
inside each response's `scenario` field (`ScenarioResult`).

## What connects to what

```text
roles.json: role:data_analyst
  task_ids -> taxonomy.json: task:data_cleaning, task:routine_reporting
  role_id  -> role_skills.json: the five baseline skill requirements

trend_signals.json:
  task_interpretations -> existing role/task IDs -> cited signals -> dated sources

scenarios.json:
  existing role/task/skill IDs -> hypothetical adjustments -> ScenarioResult
```

Scenario skills must already be requirements for the selected role. This example
does not silently add spreadsheets or new AI skills to Person 1's requirements.

## Evidence and limitations

The baseline cites Anthropic's report published **2025-09-15**, reviewed through
the public webpage on **2026-10-20**, and the **2026-01-15** report admitted by
the live refresh pipeline:
https://www.anthropic.com/news/anthropic-economic-index-september-2025-report

https://www.anthropic.com/research/anthropic-economic-index-january-2026-report

It provides context about collaboration/delegation and organizational context.
The two task mappings are explicitly **team interpretations**, not measurements
of cleaning or reporting automation. The ledger stores our own paraphrases and a
link, not a copy of the article or underlying data. No blanket article reuse
license has been verified. This is a historical release, not a claim to use the
latest research. The January release adds a contextual collaboration signal,
not task-specific automation measurements. Source dates, coverage and limitations are included in every
relevant response.

The role/task assignments and requirement weights remain **synthetic**.
`catalog_synthetic=true` applies in all three modes. `scenario.synthetic=false`
only means no hypothetical scenario adjustment is being applied; it does not
turn the catalog into observed data. Person 5 should display both provenance
flags and render task mappings as interpretation. No employment growth,
job-loss rates, local adoption estimates, or personal fit changes are computed.

## Priority calculation for Person 4

This example follows the specification's additive formula:

```text
adjusted_priority = clamp(baseline_priority + adjustment, 0, 1)
```

It exposes additive adjustments rather than multipliers. This is an initial
contract proposal for Person 4 to review before integration. Actual gaps still
come from Person 2: a raised priority does not mean a user lacks that skill.

| Skill | Baseline | Moderate hypothetical | Rapid hypothetical |
|---|---:|---:|---:|
| Python | 0.70 | 0.75 | 0.80 |
| SQL | 0.90 | 0.90 | 0.90 |
| Statistics | 0.80 | 0.90 | 1.00 |
| Data visualization | 0.80 | 0.80 | 0.80 |
| Communication | 0.60 | 0.70 | 0.80 |

All adjustment magnitudes are authored demo assumptions. Rationale: assume more
AI-assisted drafting/cleaning, then emphasize checking results and explaining
their limitations. Each request starts from the unchanged baseline, so switching
back restores the original values exactly. `applied_adjustment` reports the
actual delta after clamping.

## Errors and next milestone

Unknown role: `KeyError`. Unknown or unsupported scenario: `ValueError`.
Missing evidence mapping: `insufficient_evidence`, with no unrelated citations.
Invalid or uncited evidence fails validation; hypothetical records cannot be
loaded as real sources or signals. Person 5 owns HTTP error mapping and routes.

The bounded refresh pipeline and live before/after demonstration are now
implemented: see [the refresh guide](ROLE_3_EVIDENCE_REFRESH.md). Still required
for broader coverage: review of newer and more task-specific evidence, UI wiring,
and expansion beyond Data Analyst after contract coordination with Persons 1,
4 and 5. No HTTP endpoint is added by this module.
