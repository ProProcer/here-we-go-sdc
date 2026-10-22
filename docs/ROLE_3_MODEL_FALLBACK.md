# Low-cost model fallback for Role 3

The default primary model is now `gemini-3.1-flash-lite`. The environment-loaded
client tries the following order when a request encounters a temporary availability
or transport failure. Both review passes retain the existing grounding, schema,
semantic-challenge and human-approval checks.

| Order | Model ID | Standard text input / output, USD per million tokens |
|---|---|---|
| Primary | `gemini-3.1-flash-lite` | $0.25 / $1.50 |
| 1 | `gemini-3.5-flash-lite` | $0.30 / $2.50 |
| 2 | `gemini-3.6-flash` | $0.75 / $3.75 |
| 3 | `gemini-3.8-flash` | $0.75 / $3.75 |

Prices were checked on 2026-10-22 against [Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing).
The two Flash prices are introductory rates through December 31, 2026. Eligible
free-tier calls remain subject to Google's model access and quota rules; this
configuration does not change the account's billing tier. Equal-price Flash
models are ordered by the observed compatibility checks: 3.6 passed, whereas
3.8 returned temporary unavailability during this check.

## Why the other proposed models are not enabled

- **Gemini 2.5 Flash-Lite** is cheaper ($0.10 / $0.40), but this key's generation
  request returned HTTP 404 with a provider message that it is unavailable to
  new users. Gemini 2.5 Flash also returned 404. Listing a model in `ListModels`
  did not establish generation access. Google's [model catalog](https://ai.google.dev/gemini-api/docs/models)
  documents restrictions on access to the 2.5 models.
- **Gemma 4 26B A4B** has the ID `gemma-4-26b-a4b-it` and free hosted pricing.
  Both attempts to use the required native JSON-schema request returned HTTP 500,
  so compatibility could not be established. This does not prove Gemma cannot
  generate JSON; it is left out until its integration can be verified. The client
  currently accepts Gemini IDs only. See [Gemma API documentation](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api).

## Bounded behavior

- Each logical generation tries each distinct configured model at most once.
  The default chain permits at most four HTTP generation attempts per pass.
- Fallback applies only to HTTP 408, 500, 502, 503, 504 and transport failures.
  It uses short exponential delays with jitter (about 1, 2, 4 seconds for the
  default chain), a 90-second budget checked before starting another attempt,
  and network timeouts capped at 45 seconds or the remaining budget.
- HTTP 400/401/402/403/404, quota/rate-limit 429 and redirects stop immediately.
  Changing models must not conceal billing, authentication, configuration or
  access problems. No extra quota is purchased or key rotated.
- Invalid JSON, blocked/truncated output, schema failures and downstream
  grounding/semantic failures never cause a switch to another model. The pipeline
  must not keep asking models until one endorses an unsupported claim.
- A successful fallback continues the same pending review; it does not approve
  a source, finding, skill mapping or numerical learning-priority change.
- If the chain is exhausted, the batch remains pending and the failure is visible.
  Successful work in other batches remains saved. Fallback cannot guarantee
  availability when the whole service or network is unavailable.

This follows Google's [bounded retry guidance](https://ai.google.dev/gemini-api/docs/troubleshooting).
Custom temperature/top-p settings are omitted for compatibility with the newer
models. The original API key stays in the authentication header sent only to
the fixed Google API host, with redirects disabled. Error bodies, prompts and
credentials are not logged.

## Configuration and provenance

```dotenv
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FALLBACK_MODELS=gemini-3.5-flash-lite,gemini-3.6-flash,gemini-3.8-flash
```

GitHub Actions reads repository variables with these names, using these defaults
when absent. Set `GEMINI_FALLBACK_MODELS=none` to disable fallback. Local CLI runs
read the process environment, not `.env` automatically. Directly constructed
clients can supply an explicit fallback tuple; their default remains no fallback.
Model IDs are validated before any network request, and duplicate IDs are skipped.

The requested primary stays fixed during a run so fallback does not change the
cache identity halfway through a batch. Source and skill review records include
the actual returned models and sanitized per-pass request attempts. Source briefs
display the answering models and actual request count. Skill briefs display the
answering models, with complete attempt details in the JSON artifact. Legacy
candidate extraction continues to record the actual successful model version.
The two passes may use the same model and are not independent empirical evidence.

Changing the primary model makes the existing model-specific caches stale under
their normal rules. Already accepted evidence and historical records are preserved;
the daily caps still limit new source reviews and skill batches. A fallback order
change alone does not discard a previously valid cached result. Actual model
provenance stays available for later human review.

Verification on 2026-10-22: **218 tests passed**, changed Python files passed Ruff,
and workflow configuration and changed-file credential checks passed. A live
review of the public synthetic fixture encountered real primary 503 responses,
fell back to 3.5 Flash-Lite for both passes, and produced two grounded pending
findings. A second live smoke check after a simulated primary 503 also returned
valid JSON from the fallback. Neither check approved or changed accepted evidence.
