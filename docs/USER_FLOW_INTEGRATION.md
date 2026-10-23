Current provider policy: Groq `openai/gpt-oss-120b` is primary for all AI tasks,
using `GROQ_API` from local `.env`. RunPod GLM is second and Gemini is the final
backup. This supersedes the earlier RunPod-primary deployment notes below.
See [AI provider configuration](AI_PROVIDERS.md).

# ikiguy user-flow integration

The React app uses `/api/v2` and the real O*NET catalog through `CareerBackend`.
Run `.venv/Scripts/python.exe -m src.main` and open http://localhost:8000.
Rebuild frontend changes with `npm --prefix frontend run build`.

## 1. Automatic skill levels

CV intake now tries RunPod GLM first, with Gemini as backup, using extracted skill evidence, returning a level,
confidence, explanation, evidence references and actual model identifier. The
review screen displays the applied estimate by default. A manual selector opens
only after **Correct this estimate**. Added skills retain their existing manual
entry controls. A failed assessment shows a specific status and **Retry AI assessment**. It never automatically
confirms skills. The existing Add a skill flow is preserved.

The web app loads known local `.env` settings without overriding host environment
values. Replit Secrets continue to work. Never put keys in the frontend. Set
`RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, and `RUNPOD_MODEL` for the primary model,
with `GEMINI_API_KEY` / `GEMINI_MODEL` reserved for backup. RunPod requires a real
vLLM/OpenAI-compatible GLM endpoint; the starter echo handler cannot assess skills.
See [shared model routing and deployment status](AI_PROVIDERS.md).
An earlier single-skill fictional Python probe succeeded on 2026-10-23; that
probe did not verify the full uploaded/sample CV flow. The current live follow-up
is described under RunPod account checks below.

One compact request covers every extracted skill, up to 100. Oversized profiles are rejected clearly rather than silently truncated. Groq is attempted first;
a service failure can use one Gemini backup request. Further skills remain available for
manual review. Missing keys, invalid responses or service failures leave levels
unknown with a visible explanation. A skill name alone is insufficient for a
proficiency estimate. Only extracted skill passages go to the model; use fictional
CVs. The original upload is discarded.

**Your action:** upload again or use Retry AI assessment; review and confirm the
claims. Provider connectivity and a functioning endpoint are required. Fallback to Gemini is now explicitly configured and identified in the result;
the shared routing policy covers background research as well as CV assessment.

## 2. Skills to explore

Matching checks canonical skill IDs against confirmed profile skills. A CV may
describe reading reports without containing the exact catalog label “Reading
Comprehension”; absence is not evidence of inability. Importance 0.80 is an O*NET
occupational importance rating of 4/5, not a user score or skill deficit.

Role details now explain that the user has not said whether a skill describes
their experience. AI level estimation and the user confirming a claim are separate
actions. The Review and confirm skills button returns to the unchanged Add a skill flow.

**Your action:** return to review, use the unchanged Add a skill search if the
skill is absent, tick its confirmation box, then explore careers again. Matches
and roadmaps recompute from the revised profile. Confirm only actual experience.

## 3. AI outlook and evidence

The committed source-to-task ledger has contextual mappings for Business
Intelligence Analysts. Shared skill and role-impact stores expose only approved
records, and their approval stores are currently empty. This explains the empty
states for other occupations; the frontend cannot create reviewed evidence. The
current real ledger has one source, two task mappings and zero source-to-skill
chains. The Source-to-skill reasoning heading now includes its actual record count.
Unassessed pairs are distinguished from proposed connections awaiting approval;
zero approvals does not mean a reviewer rejected the findings.

Every role now also displays a dated ILO research source as **general context**.
It is explicitly separate from reviewed role findings and does not change fit or
research-based numerical priorities. No ISCO-to-O*NET exposure mapping is claimed.

**Your action:** use `Review Role 3.cmd` to load the report and separately review
sources, skill connections and role impacts. Follow
[the review menu guide](ROLE_3_REVIEW_MENU.md) and
[finding admission guide](ROLE_3_APPROVAL.md) to extend the actual evidence ledger.
Persist approved records into the deployed checkout. Do not approve every item
just to populate the UI. Refreshing a source alone does not create new mappings.

## 4. Learning resources and SDGs

The real catalog now contains six provider-checked free OpenLearn courses. The
planner selects them by actual skill IDs, prerequisites and budget. Curriculum
coverage is an application interpretation, not a certificate of job readiness.
Course content, zero-cost access, duration and participation recognition were
checked against provider pages on 2026-10-23; see each course's evidence URL and
validation notes in `data/processed/onet/31.0/courses.json`.

Uncovered skills keep explicit practice activities and a provider-catalog link;
the app does not invent a specific course. Live course discovery remains
unconfigured. Costs and hours refer to selected courses, not uncovered self-study.

SDG 4.4 remains the general employment-learning connection. Conditional mappings
now add health workforce (3.c), teacher capability (4.c), research/innovation
(9.5) and access to justice (16.3) for relevant roles and planned skills. The UI
distinguishes learning-pathway links from role-application links. All additional
connections are inferred pathways with conditions, not measured SDG outcomes.
Role connections now use the occupation's requirements, including already-confirmed
skills, independently of remaining learning gaps. This fixes role-specific SDGs
disappearing after their trigger skills were confirmed. SDG rules are curated in
JSON, rather than generated by AI or randomly selected for visual variety.

**Your action:** extend the verified course catalog for specialist skills and
optional software; check provider content, access, prices, duration, prerequisites
and location availability first. Extend `sdg_mappings.json` with supported role
and skill IDs and an official UN target URL when more occupational coverage is
needed. Identical SDGs can legitimately recur for similar goals and roles.

## 5. Baseline / Moderate / Rapid

All real-catalog occupations with requirements now support the three options.
The existing BI-specific scenarios retain their configured adjustments. Other
roles use a transparent generic stress test: Moderate adds 0.08, Rapid 0.16 to
required checking, learning and communication priorities, capped at 1.0. Other
priorities stay unchanged. Assumptions are shown in the roadmap.

Changing a scenario reloads outlook and plan together. Baseline restores the
original priorities; personal fit, approved research and confirmed skills do not
change. Already-confirmed skills are absent from the roadmap, so a scenario may
show no change when all affected gaps have already been addressed.

**Your action:** no configuration is needed. Build a new roadmap and switch
scenarios. For more role-specific stress tests, add explicit role/scenario pairs
to `data/synthetic/onet_scenarios.json`; keep them labeled hypothetical.

## Source checks

- [ILO occupational exposure study](https://www.ilo.org/publications/generative-ai-and-jobs-refined-global-index-occupational-exposure)
- [OpenLearn thinking course](https://www.open.edu/openlearn/education-development/extending-and-developing-your-thinking-skills)
- [OpenLearn communication course](https://www.open.edu/openlearn/money-business/effective-communication-the-workplace)
- [UN health targets](https://sdgs.un.org/goals/goal3)
- [UN education targets](https://sdgs.un.org/goals/goal4)
- [UN innovation targets](https://sdgs.un.org/goals/goal9)
- [UN justice targets](https://sdgs.un.org/goals/goal16)

## RunPod account check on 2026-10-23

`python -m scripts.check_runpod` reads endpoint metadata and account balance; it
runs no inference and creates no resources. The locally stored key authenticated
successfully and reported **USD 25**, not USD 20. The configured endpoint returned
HTTP 404, and listing the account's Serverless endpoints returned zero endpoints.
These are account credits; a working deployed GLM model has not been verified.

To use RunPod inference, create an appropriate GLM/vLLM endpoint in the account,
set its actual ID and served GLM model name. The shared policy already prioritizes RunPod.
The user approved deployment; the endpoint has now been created and completed
a direct GLM inference test. Running workers consume RunPod credit. See [RunPod model API configuration](https://docs.runpod.io/serverless/vllm/openai-compatibility).

The preview was subsequently restarted with approved network access for the
requested RunPod-primary/Gemini-backup policy. A full fictional sample CV now
receives 10 automatic skill assessments directly through the deployed RunPod GLM
model. The final web check completed in approximately 68 seconds, applied the
levels after validating their evidence references, and reported `used_backup=false`.
The approved GLM endpoint is deployed and has completed a direct inference
test. GPU capacity throttling can still invoke Gemini backup; the client cancels
its own pending job when its time budget expires. See the current [provider guide](AI_PROVIDERS.md).
