# AI outlook and evidence

This section answers: **How might AI change this career's tasks, and what
could I practise to prepare?** It connects fetched research to the selected
occupation's actual tasks and catalog skills.

Each supported card shows a research finding, a possible task implication,
a learning action, and a linked source with its publication and fetch dates.
The task implication is labelled as an AI interpretation. The supporting
quotation can be expanded. Human-reviewed research remains a separate,
expandable part of the career drawer.

## Updatable sources

| Publisher | Feed | Use |
|---|---|---|
| Google Research | https://research.google/blog/rss/ | AI research and capabilities |
| Microsoft Research | https://www.microsoft.com/en-us/research/feed/ | AI research and applications |

Feed URLs, keywords and the 90-day publication window are configured in
`data/sources/discovery_feeds.json`. The app fetches RSS/Atom entries and,
where needed, bounded article excerpts. Titles and dates are parsed from
external responses rather than supplied as a fixed list.

While the application is running, a scheduler checks for sources overdue
for their 24-hour refresh and retries failures after an hour. The **Refresh
trends** button also requests an external fetch. Each feed has a fetch status,
timestamp and response hash. A fetch failure preserves previous records and
displays their original dates with a cached status. The app does not claim
that a failed attempt refreshed its sources.

The runtime cache is `.trend-cache/state.json`. The redistributable fallback
in `data/snapshots/trends/live/latest.json` contains fetched metadata and short
supporting excerpts. This snapshot allows startup without network access;
the external fetch mechanism makes the layer updatable.

Feed validation rejects HTML or other non-feed XML returned by a publisher;
failed checks retain the last good sources and fetch date. Career changes reset
the outlook disclosure, and late refresh responses from a previous career are
ignored so that they cannot replace the newly selected career's research.

## Role connections and limits

Articles are ranked by word overlap with the occupation and its tasks. A model
can propose up to three connections using supplied source, task and skill IDs.
The **How much research was assessed?** summary separates stored articles,
the top six selected articles, excerpts actually assessed by AI, and career
connections shown. Selected articles with fewer than 80 characters of source
text are not sent to the model. Each submitted excerpt is capped at 1,500
characters; this is not a full-article review.

**How sources were assessed** shows completed article assessments with source
dates. Other fetched articles are in a separate collapsed disclosure. Every submitted article must have an AI explanation:
connected, indirect relevance, insufficient detail, no clear connection in the
excerpt, or potentially related but not selected for a card. Other articles
are explicitly marked as not assessed. A connection cap of three means an
omitted article may still be useful. These reasons are AI judgments about
excerpts, not findings established by the publishers.

Validation requires exactly one assessment per submitted article and checks
that connected assessments match the displayed interpretations. Missing,
duplicate or unknown article assessments are rejected. Assessments persist
with interpretations. Updates to the selected excerpts trigger a fresh check;
changes to other articles or fetch timestamps alone do not. The last completed
result stays visible during updates or provider failures, labelled with its
original assessment and citation dates. Archived input excerpts allow earlier
results to be validated without substituting newer source text. Older
caches retain their supported cards, label missing assessment details as
unavailable, and request a fresh analysis when opened in an active session.

Validation rejects unknown IDs and quotations absent from the supplied source
text. Changed selected excerpts or catalog data mark the previous result as
needing an update rather than erasing it.
These checks establish citation traceability, not human approval or certainty
about future employment. If no supported connection is produced, the UI shows
the fetched sources without inventing career implications.

An unsupported quotation withholds its interpretation card and marks that
article **Connection withheld · citation not verified**, with an application
evidence-check explanation. It does not discard the completed article
assessments or expose the unverified claim. Unknown source/task/skill IDs,
duplicate interpretations and inconsistent assessment coverage still reject
the batch.

Before the first completed result, the UI shows a single progress panel and
optional dated source links, without zero-result counts or a list of pending
articles. After 30 seconds it explains that the check is taking longer. Failed
or deferred checks have a **Retry assessment** action, which does not refetch
the feeds. Model requests and their validation retry share a 45-second budget
across provider fallbacks. The queue allows two pending careers and rejects
work that would wait more than 45 seconds. Availability failures remain
distinct from a completed assessment that finds no supported connections.

Research feeds satisfy the requirement's research-feed source option. This
implementation does **not** measure vacancies, salary changes or Malaysian
hiring demand. Personal fit scores remain based on the user's skills and
preferences. Live AI interpretations do not automatically modify reviewed
learning priorities or the roadmap; those use the separate evidence policy.

## Running and verifying

From the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.refresh_live_trends --export-snapshot
# Also generate an interpretation using the configured model provider:
.venv/Scripts/python.exe -m scripts.refresh_live_trends --export-snapshot --analyze
```

The default demonstration occupation is Business Intelligence Analysts.
Use `--role-id` for another catalog occupation. External retrieval needs
network access; interpretation additionally needs model credentials.

Read endpoints are `GET /api/v2/trends/status` and
`GET /api/v2/roles/{role_id}/trends`. The session-authenticated refresh endpoint
is `POST /api/v2/roles/{role_id}/trends/refresh`. It returns immediately while
the external fetch runs; the UI polls for completion.

`tests/test_live_trends.py` covers changed external responses, dates,
deduplication, cache fallback, grounding and unchanged fit scores.
`tests/test_web_app.py` covers the HTTP endpoints. The opt-in browser test in
`tests/test_browser.py` verifies visible citations and refresh behaviour using
explicit fixtures. `scripts/verify_live_trends_browser.py` verifies an actual
external refresh through a running local app and records results under
`docs/verification/`.
