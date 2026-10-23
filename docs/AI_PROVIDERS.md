# Groq GPT-OSS-120B primary, RunPod GLM and Gemini backups

Every application AI task uses `src.intelligence.models.ModelClient`, including
CV assessment, source review, skill evidence, role evidence, extraction, proposals,
and background discovery. Matching, scenarios, courses and SDG selection remain
deterministic. Changing providers does not approve research findings.

## Local configuration

The app reads known settings from ignored local `.env` without overriding host values.

```dotenv
LLM_PROVIDER=groq
LLM_FALLBACK_PROVIDER=runpod,gemini
GROQ_API=<your Groq key>
GROQ_MODEL=openai/gpt-oss-120b
RUNPOD_API_KEY=<your RunPod key>
RUNPOD_ENDPOINT_ID=<your deployed GLM endpoint>
RUNPOD_MODEL=zai-org/GLM-4.7-Flash
GEMINI_API_KEY=<your final backup key>
GEMINI_MODEL=gemini-3.1-flash-lite
```

`GROQ_API_KEY` is also accepted as an alias. `GROQ_API` takes precedence.
Groq uses its fixed HTTPS endpoint and strict structured outputs, with low reasoning
effort and reasoning excluded from responses. All object fields are explicitly
required by its JSON schema. Application validation and evidence checks still apply.
See [Groq structured outputs](https://console.groq.com/docs/structured-outputs).

## Fallback and provenance

Groq is first, RunPod GLM second, Gemini last. Only availability failures such as
rate limits, authentication failures, connection errors and transient server errors
try the next provider. Invalid JSON, incomplete responses, failed schema checks and
invalid evidence references stop the request. Actual provider, model and attempts
are recorded; the UI labels backup assessments accurately.

Interactive budgets are 20 seconds for Groq, 90 for RunPod and 30 for Gemini.
Background budgets are 45, 90 and 45 seconds respectively. The browser allows
210 seconds per request, covering bounded OCR plus the fallback chain. Gemini makes one backup request without a model cascade.
Missing provider credentials skip that provider. Legacy `LLM_PROVIDER=runpod` retains
the earlier RunPod/Gemini policy for compatibility.

GitHub Actions reads `GROQ_API` from repository secrets; configuring local `.env`
does not upload keys or publish local changes. The existing setup script supports
this secret when explicitly invoked.

## Groq verification on 2026-10-23

The configured local key successfully called `openai/gpt-oss-120b`. The web API
assessed all ten fictional sample-CV skills in 5.67 seconds with `provider=groq`
and `used_backup=false`. A live Edge browser check confirmed that the same
successful Groq assessment message appears in the review screen. No real CV
was sent for these checks.

## Prepared RunPod deployment

The reviewable configuration is `runpod/glm_deployment.json`:

- official worker image `runpod/worker-v1-vllm:v2.30.1`;
- official `zai-org/GLM-4.7-Flash` weights, BF16 on one A100 80 GB GPU;
- 65,536-token context, one sequence and one concurrent request per worker;
- `glm45` reasoning parser, request logging disabled;
- zero minimum workers, one maximum worker, five-second idle timeout;
- 180-second endpoint execution timeout and no attached persistent volume.

The worker release/tag and model configuration were checked on 2026-10-23.
RunPod calls now use its native `/run` and `/status` job API with the worker's
OpenAI passthrough input. The application polls within its time budget and cancels
its own pending job before falling back. Thinking mode is disabled with the
model's `enable_thinking` template option for bounded structured responses.

GPU use consumes account credits. This configuration limits concurrency and idle
workers; it does not impose a dollar spending cap. Cold starts may trigger Gemini
backup while the RunPod worker loads. The application explicitly requests cancellation on a client time budget expiry;
the endpoint execution timeout also bounds processing.

Prepare/review without changing the account:

```powershell
.venv/Scripts/python.exe -m scripts.deploy_runpod_glm
```

After deployment approval:

```powershell
.venv/Scripts/python.exe -m scripts.deploy_runpod_glm --apply
```

The apply command creates a private template and endpoint, preserves the API keys,
updates the endpoint/model settings in local `.env`, and writes a local receipt
under `.role3-review/`. It reuses an existing endpoint with the exact expected name
and worker limits. It never starts a standalone Pod or provisions a network volume.

## Verification and current deployment status

The approved endpoint was deployed on 2026-10-23 and local `.env` now contains its
actual endpoint ID and served model. Zero minimum workers, one maximum A100 80 GB
worker, five-second idle shutdown and FlashBoot are enabled. The validated local
deployment receipt is `.role3-review/runpod-deployment.json`.

Direct RunPod inference returned a valid JSON response from the configured GLM
model without Gemini. A full fictional CV model request also produced all 10
canonical skills with a valid response schema: 1.623 seconds queue delay, 57.838
seconds execution, and 708 completion tokens with no reasoning tokens. Detailed
model-level verification is in `.role3-review/runpod-full-cv-completion.json`.
The final live web check completed in 68.22 seconds: all 10 skills received
applied AI metadata from RunPod, grounding validation passed, and `used_backup`
was `false`. Its summary is `.role3-review/runpod-web-final-check.json`.

The first model download/load took approximately 4.5 minutes and used 55.83 GiB
of GPU memory. Host capacity has been intermittent: a throttled worker cannot
obtain its host GPU, and requests may queue even when earlier status snapshots
reported a ready worker. This triggers the explicitly reported Gemini backup
when the application time budget is exhausted. The client cancels its own pending
job; timeout fallbacks do not leave an unbounded queue of abandoned requests.

The RunPod balance was approximately USD 24.29 after deployment and
verification activity, from USD 25 before deployment. This is a point-in-time
account reading, not a spending cap.

## GitHub Actions

The workflow now passes `RUNPOD_API_KEY` as an encrypted repository secret and
`RUNPOD_ENDPOINT_ID` / `RUNPOD_MODEL` as repository variables. Gemini credentials
remain backup credentials. The model-dependent stages can run when RunPod alone
is configured; they no longer require a Gemini key to be present.

The existing configuration helper now supports both model keys and the RunPod
variables, preserving existing repository values:

```powershell
uv run --no-project --with pynacl python -m scripts.configure_role3_actions --configure-secret
```

This change updates workflow code and the helper locally. It does not upload keys,
push code, or claim that the remote workflow has switched before publication and
repository settings are configured.

## Provider references

- [RunPod GLM-4.7-Flash deployment guide](https://www.runpod.io/articles/guides/run-glm-4-7-flash-on-runpod)
- [RunPod model endpoint compatibility](https://docs.runpod.io/serverless/vllm/openai-compatibility)
- [Official model configuration](https://huggingface.co/zai-org/GLM-4.7-Flash)

## Database validation for CV assessment

Before a CV assessment, unknown skill IDs are removed against the active catalog,
and canonical names replace untrusted names. The model receives only those IDs,
with their database kind (general or software), definition and allowed levels.
The response schema constrains IDs and evidence indices. After generation, IDs
outside the database or CV allowlist are discarded; the retained profile is
validated again against the same catalog. Unknown output cannot become a new
skill, and no AI result confirms a claim on behalf of the user. This assessment
estimates levels of recognized CV skills; it does not invent a new skill taxonomy.

Groq receives the structured schema once through response_format, rather than
also embedding it in the system prompt. This reduces request token consumption.
The test runner spaces live calls because the observed account quota was 8,000
tokens per minute; that observation is not a promise of an account's future quota.

The earlier ten-skill sample receipts predate the extraction correction that stops interpreting Computer Science as a separate Science claim. The current sample contains nine catalog-backed skills.
