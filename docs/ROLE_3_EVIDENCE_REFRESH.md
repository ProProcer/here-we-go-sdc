# Role 3: reviewed evidence refresh

The pipeline refreshes one explicitly approved public report. It uses Python's
standard library and the existing Pydantic dependency; no API key, LLM, GPU,
additional package or server is needed.

## Run

```bash
python -m src.intelligence.feeds
python -m src.intelligence.outlook
python -m unittest discover -s tests -v
```

The refresh command returns JSON with a status:

| Status | Meaning | CLI exit code |
|---|---|---:|
| `updated` | Verified source changed the validated ledger | 0 |
| `unchanged` | Source verified; ledger already matches | 0 |
| `cached` | Refresh failed; prior validated ledger remains available | 1 |
| `unavailable` | Refresh failed; no valid cached ledger is available | 1 |

Outlook reads the cache without network access. Person 5 can call
`src.intelligence.feeds.get_refresh_status()` to display the last attempt's
message and timestamp; show a warning for `cached` and `unavailable`. A successful
fetch does **not** make an old report current labor-market evidence. Display
publication dates and source limitations even after success. No scheduler is
configured yet; run refresh manually or through the deployment's scheduler.

## Validation and storage

`data/sources/anthropic_january_2026.json` is a human-reviewed source definition:
approved URL, publication date, visible-page markers, a short original paraphrase,
and explicit role/task interpretations. It is distinct from synthetic scenarios.

The pipeline:

1. Validates the review's real-evidence flags and reference IDs.
2. Fetches only the allowlisted HTTPS report, without redirects. Response size
   is capped at 2 MiB, socket operations have a 15-second timeout, and an elapsed
   time check runs between reads. These are transport bounds, not a strict
   process-wide deadline.
3. Checks HTML content type, the visible report heading, publication marker and
   reviewed claim markers. Script/style content is excluded from those checks.
4. Merges the reviewed signal, preserving the previous report and evidence links.
   Validates role/task references against Person 1's catalog.
5. Saves a timestamped **structured evidence snapshot**, fetched-body SHA-256,
   response byte count and review-definition SHA-256 under
   `data/snapshots/trends/`. Raw article HTML is not persisted or redistributed.
6. Atomically replaces `data/processed/trend_signals.json` only after successful
   validation and snapshot writing. Records the attempt in `last_refresh.json`.

These marker checks verify that a previously reviewed statement remains on the
expected report page. They do not independently establish source truth or
interpret arbitrary new findings. Changed claims, new URLs and new publications
need a reviewed source definition and explicit allowlist update. This is a
bounded reviewed-source pipeline, not an automatic latest-news discovery feed.
Only one refresh process should run at a time; concurrent writes are not locked.

## Actual dated-input demonstration

The live fetch on **2026-10-20** successfully admitted the report published
**2026-01-15**, supplementing the earlier **2025-09-15** contextual example.
The newer report's platform-level collaboration finding changes the cited
signals and both task interpretations. It does not establish measured cleaning
or reporting automation.

Artifacts:

- `data/demo/data_analyst_evidence_before_refresh.json`: the prior local example's
  reviewed ledger, preserved before regenerating outlook responses.
- `data/demo/evidence_refresh_comparison.json`: before/after tasks and source IDs,
  with the relative path to the actual live-fetch snapshot.
- `data/demo/data_analyst_outlooks.json`: updated responses for all three modes.

Synthetic scenario priorities remain unchanged by this source addition. The new
contextual observation does not justify inventing numerical weight changes.
Tests separately verify scenario sensitivity, source input propagation, cache
preservation on failures, invalid citations, synthetic isolation, URL/redirect
restrictions, oversized responses, and missing date/claim markers. Mock HTML in
tests stays in temporary directories and is never treated as a real fetch.

## Next integration work

Person 5 owns displaying refresh state, dates, citation links and interpretation
labels. Person 4 should review the additive priority contract. Broader source
coverage and more task-specific evidence remain future work; neither historical
report is represented as the latest available research.
