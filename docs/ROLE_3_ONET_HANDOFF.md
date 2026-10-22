# Role 3 real-catalog evidence handoff

For daily discovery and future reviewed numerical adjustments, see the
[discovery and learning-priority policy](ROLE_3_DISCOVERY_AND_PRIORITIES.md).
The current source-only example below still produces no numerical adjustment.

The offline backend handoff is ready for **Business Intelligence Analysts**,
`role:onet_15_2051_01`. It contains one live-verified source finding and two
contextual task interpretations. The other 15 tasks retain insufficient evidence;
this is a scoped demo, not evidence coverage for all 910 occupations.

## Artifacts and provenance

- Source definition: [`onet_bi_ds_star_2025.json`](../data/sources/onet_bi_ds_star_2025.json).
- Assistant research review: [`onet_bi_evidence_review.json`](../data/review/research/onet_bi_evidence_review.json).
- Accepted real ledger: [`trend_signals.json`](../data/processed/onet/31.0/trend_signals.json).
- Live fetch receipt: [`20261022T073637257329Z_f74de90b919d.json`](../data/snapshots/trends/onet/20261022T073637257329Z_f74de90b919d.json).
- Complete offline response: [`onet_role3_handoff.json`](../data/demo/onet_role3_handoff.json).
- Combined Persons 2–4 example: [`onet_backend.json`](../data/demo/onet_backend.json).

The source is [Google Research's DS-STAR report](https://research.google/blog/ds-star-a-state-of-the-art-versatile-data-science-agent/),
published **2025-11-06** and fetched **2026-10-22 UTC**. Its `DS-STAR` and
`Evaluation` sections support the finding. The receipt stores the response hash,
fetch time, definition hash and accepted ledger, without redistributing the page.

This definition was authored and checked by the interactive assistant under the
request to complete the handoff. It uses the existing source-definition refresh
workflow, not Gemini candidate approval. No human reviewer identity, human
sign-off, paid model run or independent semantic audit is claimed. The earlier
mock research draft remains historical and was not silently approved or relabeled.

## Person 5: consume and display

```python
from src.backend import CareerBackend
from src.intelligence.feeds import ROOT, get_refresh_status
from src.intelligence.impacts import get_evidence_chain_response

backend = CareerBackend()
role_id = "role:onet_15_2051_01"
outlook = backend.outlook(role_id, "baseline")
response = outlook.model_dump(mode="json")
status = get_refresh_status(ROOT / "data/snapshots/trends/onet/last_refresh.json")
implications = get_evidence_chain_response(role_id, catalog=backend.catalog)
```

Use `task.signal_ids -> signals.source_id -> sources.source_id` for citations.
Display the task's `interpretation`, `mapping_basis` and `evidence_scope` alongside
the source URL, publisher, publication date, retrieval date and limitations.

| Task | Expected evidence status |
|---|---|
| `task:onet_16150` — reporting | `contextual_evidence` |
| `task:onet_16145` — output testing | `contextual_evidence` |
| Other BI tasks | `insufficient_evidence` |

The interpretation text carries its assumptions and human responsibilities.
`contextual_evidence` means a cited team interpretation, not a measured task effect.
Keep the historical research classification visible; do not call it current job
demand. Use the **real-catalog status path above**: the no-argument status helper
still selects the legacy mock refresh log. A failed refresh must show its cached
warning even when the last successful receipt remains available.

Render `available_scenarios` for the selected role. BI supports baseline,
`moderate_ai_change` and `rapid_ai_change`; the latter two remain hypothetical
stress tests. Switching modes changes authored learning priorities only. An
uncovered occupation has no borrowed BI finding and rejects BI-only scenarios.

## Person 4: priorities and skill limitations

Continue consuming the reviewed match's actual gaps and the selected outlook's
`scenario.skill_priorities[].adjusted_priority`. The source finding introduces
no numerical adjustment. Baseline remains O*NET Importance/5; existing scenario
adjustments remain separately authored assumptions. Personal fit is preserved.

Imported tasks have no reviewed task-to-skill edges. Therefore
`get_evidence_chain_response()` correctly returns `insufficient_evidence` and
an empty `chains` list. This does **not** mean task citations are absent.
Do not invent edges or infer skill increases from the report. Skill-specific
evidence chains require a separately reviewed mapping and appropriate evidence.
Verified course discovery and UI/deployment remain their respective owners' work.

## Refresh and reproduce

```bash
python -m src.intelligence.feeds --catalog onet --review data/sources/onet_bi_ds_star_2025.json
python -m scripts.build_onet_role3_demo --snapshot PATH_PRINTED_BY_REFRESH
python -m src.backend
python -m unittest discover -s tests -q
```

Only the refresh command fetches the source. The handoff builder rejects a
snapshot that differs from the current ledger or whose source definition changed
since verification. It reads cached data and invokes no external model. Review
the research record again when changing the finding or its task interpretations.
The builder does not itself grant approval or establish semantic correctness.

The refresh checks heading/date/claim markers; it cannot detect every semantic
change to a webpage. A successful fetch proves transport and marker checks,
not an independent audit of the underlying study or interpretation.

## Verification on 2026-10-22

- Live source refresh returned `updated`; source metadata and real task IDs passed validation.
- Both offline example builders completed successfully.
- All **162 unit/integration tests passed**. Coverage includes unsupported-task
  and occupation isolation, unchanged scenarios and planning results after adding
  evidence, receipt consistency and rejection of unverified definition edits.
- Ruff checks and formatting passed for changed Python files; `git diff --check` passed.
- The catalog snapshot test now compares UTF-8 text with normalized newlines,
  retaining content/formatting checks across LF and Windows CRLF checkouts.
  The source definition is pinned to LF in `.gitattributes` so its live-receipt
  byte hash survives checkout.
