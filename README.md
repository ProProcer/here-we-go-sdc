# FutureReady AI — Aiversecity Future-Ready Workforce

> **Working local prototype** for SDC Hackathon 2026, Domain 1. CV upload, skill review, real-catalog matching, scenarios and learning objectives are connected. Public deployment and real-role evidence/course coverage remain outstanding.
> An evidence-aware career navigator that connects current skills to explainable role matches, AI-change scenarios, low-cost learning pathways and UN SDG targets.

## Team Information

| Field | Details |
|---|---|
| Team name | `[ADD REGISTERED TEAM NAME]` |
| Domain | **Domain 1 — The Aiversecity Future-Ready Workforce Domain** |
| Primary SDG | **SDG 4: Quality Education (Target 4.4)** |
| Supporting SDGs | **SDG 8.2 / 8.5**, others where defensible for specific roles |
| Team leader | `[ADD REGISTERED LEADER]` |
| University | `[ADD]` |
| Number of team members | `5 planned; replace with actual registered number` |

## Official and project links

| Resource | URL / status |
|---|---|
| GitHub | `[ADD NEW REPOSITORY CREATED AFTER HACKATHON START]` |
| Replit project | `[ADD ACTUAL TEAM PROJECT]` |
| Live prototype | `[ADD FUNCTIONAL PUBLIC DEPLOYMENT]` |
| RunPod endpoint | `[ONLY IF ACTUAL GPU WORK USED]` |
| Pitch slide deck | `[ADD]` |
| 5–7 minute YouTube demo | `[ADD]` |

## Problem

AI alters tasks and occupational skill needs, but existing career advice often combines generic predictions, opaque match scores and outdated training lists. Graduates and early-career professionals need a transparent way to connect their transferable skills to suitable roles, assess evidence and uncertainty, and identify practical low-cost courses.

## Solution

Upload a **synthetic** CV or enter a fictional sample profile; review extracted skills; explore standardized roles ranked by transparent fit; inspect dated AI-job evidence and role-specific task impacts; compare a factual baseline with **explicitly synthetic** moderate/rapid disruption scenarios; generate verified and inexpensive courses in prerequisite order; understand the SDG contribution of the role and skill-building.

### Six required features

1. Skills profile intake from fictional CV/form.
2. Updatable dated AI/job-market signal layer with source provenance.
3. Explainable future-role matching plus skills gaps.
4. Ordered, affordable, resource-verified reskilling plan and time estimates.
5. Role **and skill** → justified SDG mapping.
6. Explicit multi-scenario uncertainty analysis (baseline plus hypothetical scenarios).

**Core differentiator:** new sourced evidence or a labeled counterfactual alters role outlooks and roadmap priorities in a traceable way. Personal *fit* remains separate from labor-market *outlook*.

## Implemented application stack

| Layer | Technology |
|---|---|
| UI | React, Vite, Tailwind CSS and TypeScript in `frontend/` |
| Application | Python / FastAPI / Pydantic |
| Data | Versioned JSON catalogs; expiring in-memory demo profiles |
| Matching | Exact taxonomy normalization and deterministic O*NET coverage scoring |
| CV extraction | Local PDF/DOCX/text parsing and CPU OCR for images/scanned pages |
| Hosting | **Replit is mandatory** |
| GPU | **RunPod only if GPU work is actually required**; real use proof then mandatory |

## Architecture at a glance

```text
Synthetic CV / form ──> SkillsProfile ──> Explainable role matching ──> dashboard
                                       ^                              |
Public jobs + role taxonomy ----------+                              | selected role
AI research/news + dated snapshots --> trend/outlook + scenarios -----+
                                                                      v
                                   verified course catalog --> learning roadmap + SDGs
```

Read **[`docs/PROJECT_SPECIFICATION.md`](docs/PROJECT_SPECIFICATION.md)** for full context, architecture diagrams, JSON contracts, evaluation, compliance, project structure, five roles and timetable.

## Intended repository structure

```text
README.md                     # This README adapted from supplied template
LICENSE                       # Apache 2.0
.replit / .env.example         # Real Replit config; secret names only
src/main.py                   # FastAPI entry point
src/{ingestion,profiles,intelligence,reskilling,api,schemas}/
runpod/handler.py             # Optional actual GPU inference code
frontend/                    # React screens, reusable components, styles and Vite build
data/{raw,processed,synthetic,demo}/
tests/                       # Regression and integration tests
docs/PROJECT_SPECIFICATION.md
docs/PRELIMINARY_PROPOSAL_DRAFT.md
submission/Submission Template SDC Hackathon.pdf  # ORIGINAL blank official PDF
```

The web application uses `src/api/` for HTTP adapters and `frontend/src/` for the React interface. FastAPI serves the production Vite build from `frontend/dist/`. Document readers remain in `src/profiles/`. See [Person 5 handoff](docs/PERSON_5_HANDOFF.md) for implemented interfaces and limitations.

## Team roles

| Person | Module | Main deliverable |
|---|---|---|
| 1 | Job Data / Occupation Taxonomy | Curated, dated role catalog and skill requirements |
| 2 | Synthetic CV / Skills Matching | Validated profile extraction, explainable scores and gaps |
| 3 | AI Trend / Uncertainty | Source-backed role outlook and labeled synthetic scenarios |
| 4 | Reskilling / SDGs | Verified low-cost pathway, time/cost and justified SDG mappings |
| 5 | Frontend / Integration / Replit | Complete interactive UI, integration tests and live deployment |

One of these members must also serve as the **registered team leader** to monitor official instructions and submit required materials. See the specification for interfaces and acceptance tests.

Person 1's **synthetic role catalog mock** is ready for integration. See
[`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) for fixtures, shared IDs, loader
usage and the original `GET /api/roles` adapter proposal. The application uses the
real catalog through the `/api/v2` routes documented in the Person 5 handoff.

Person 1 also supplies a **real O*NET® 31.0 catalog** with 910 occupations,
source provenance, an exclusion audit, versioned read adapters and exploratory
group/individual software coverage. Start with the
[Person 1 handoff](docs/PERSON_1_HANDOFF.md),
[consumer migration guide](docs/PERSON_1_MIGRATION.md) and
[actual evaluation](docs/PERSON_1_EVALUATION.md).
The real catalog uses schema 0.2.0; current teammate defaults retain the mock
for compatibility. Persons 2–4 now use the real catalog through
`src.backend.CareerBackend`; run `python -m src.backend` for the offline
end-to-end example. Person 5 now wraps this shared backend with HTTP routes and a CV-first interface. O*NET data are licensed
under CC BY 4.0 separately
from this repository's Apache-2.0 code. See [data sources](docs/DATA_SOURCES.md).

Person 3's **Data Analyst evidence and scenario module** is also implemented.
The current [real-catalog evidence handoff](docs/ROLE_3_ONET_HANDOFF.md) supplies
a live-verified source finding, two contextual BI task interpretations and an
offline integration response. Unsupported tasks and skill effects remain explicit.
Role 3 also includes [daily source discovery, finding review and a bounded
learning-priority policy](docs/ROLE_3_DISCOVERY_AND_PRIORITIES.md), with a GitHub
Actions review queue and explicit approval before evidence affects priorities.
An [AI-first source reviewer](docs/ROLE_3_AI_REVIEW.md) now checks retrieved
articles and study leads, challenges its draft and produces a short
[human attention brief](data/review/discovery/REVIEW_BRIEF.md).
The [shared skill-evidence layer](docs/ROLE_3_SHARED_SKILL_EVIDENCE.md) reviews
sources independently of any role, assesses new/changed skills against stored
findings, and lets new roles reuse existing approved conditional mappings offline.
Its [low-cost model fallback policy](docs/ROLE_3_MODEL_FALLBACK.md) handles temporary
model failures with bounded attempts and preserves the actual model provenance.
For a private button-based workflow, double-click **`Review Role 3.cmd`** on your
laptop. The [review menu guide](docs/ROLE_3_REVIEW_MENU.md) explains loading the
latest GitHub report, approving/rejecting items, targeted AI rechecks and saving
your reviewed decisions back to GitHub.
The [role impact checker](docs/ROLE_3_ROLE_IMPACTS.md) now shortlists roles through
supported skill connections, checks actual role tasks against stored findings,
and adds a **Role impacts** tab with separate approval, rejection and AI rechecks.
Current approved interpretations are available offline through
`CareerBackend.role_impacts(role_id)`; they do not change numerical weights.
The [first evidence-chain deliverable](docs/ROLE_3_EVIDENCE_CHAIN.md) connects a
refreshable cited finding to a proposed task interpretation and explained
Python/SQL skill implications. It includes an offline example and live-fetch
receipt; it does not constitute a deployed application or employment forecast.

Role 3 also supports [automatic candidate finding extraction](docs/ROLE_3_EXTRACTION.md)
from an approved report URL using Groq GPT-OSS-120B, with RunPod GLM and Gemini as backups. Generated findings remain in a separate
review queue until an owner checks them; accepted evidence is not changed by extraction.
The [approval CLI](docs/ROLE_3_APPROVAL.md) prepares a review plan and admits an
explicitly approved finding through the refresh pipeline, with reviewer/source
provenance and an optional separately reviewed role/task interpretation.
The [task/skill proposal stage](docs/ROLE_3_TASK_SKILL_PROPOSALS.md) uses an accepted
finding and the catalog to generate conditional implications or explain
insufficient evidence. Its outputs remain separate proposals for review.

## How to run

Use Python 3.11+ (verified locally with Python 3.13) and Node.js 22.12+. Create and activate a Python virtual environment. From the repository root, install dependencies and build the frontend once:

```bash
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m src.main
```

Open **http://localhost:8000**. Upload a fictional CV or choose **Try sample** to parse the downloadable fictional PDF. Confirm the extracted skills before exploring roles. Moderate/rapid hypothetical scenarios now work across the real occupational catalog; Business Intelligence Analysts retains its specific configured stress tests. See [user-flow integration and next steps](docs/USER_FLOW_INTEGRATION.md) for AI estimates, evidence review, course coverage and SDGs.

For frontend development, keep Python running in one terminal and run `npm --prefix frontend run dev` in another. Open **http://localhost:5173** for Vite's live updates. Vite forwards `/api` to Python on port 8000; profiles stay in backend memory. `npm --prefix frontend run build` checks TypeScript and generates the production build. Rebuild to see frontend changes on port 8000. `node_modules/`, `dist/` and build metadata are ignored; commit `frontend/package-lock.json`.

Supported uploads: PDF, DOCX, UTF-8 TXT, JPG and PNG, up to 2 MiB; PDFs up to five pages. Scanned pages and images use local CPU OCR with packaged RapidOCR models. Extraction is limited to the catalog vocabulary; always review the evidence and correct missed or mistaken skills. There is no ATS-template requirement.

The pulled real-role evidence ledger contains one source and two contextual task interpretations for Business Intelligence Analysts. Other roles retain insufficient-evidence states. Role 3's existing shared skill evidence and role-impact lookups are connected to read-only HTTP routes and expandable evidence panels. Only approved records are displayed; the committed approval stores remain empty. Reviewed learning-priority metadata and course-cache status are also shown through disclosures. The verified course catalog now includes six free OpenLearn courses; uncovered skills retain practice objectives and an explicit resource-not-found state. Evidence lookups make no Gemini calls. CV intake uses the shared Groq GPT-OSS-120B primary / RunPod GLM / Gemini backup router to estimate levels for all extracted skills (up to 100 per bounded request), with explanations for review. RunPod requires a deployed vLLM-compatible GLM model endpoint. Research review, extraction, skill mapping and role-impact jobs use the same routing policy. See [model provider setup and deployment status](docs/AI_PROVIDERS.md). Known local `.env` settings are loaded at startup. Failed assessments now show the specific failure and a retry button; manual corrections are optional. Without AI, intake still works and levels remain unknown. Background review jobs use GROQ_API; RunPod and Gemini credentials are reserved for backup.

`python -m src.main` is the deployment entry point. It binds to `0.0.0.0`, reads `PORT` (default `8000`), and uses one worker. No API key is needed for CV intake, matching or the cached learning planner.

## Deploy on Replit

1. Put the latest application files in GitHub, then open [Replit Import](https://replit.com/import) and import that repository. Import only includes committed/pushed changes. Alternatively, import a clean project ZIP containing `.replit`, `replit.nix`, `requirements.txt`, `src/`, `frontend/` (including its package lock) and `data/`; exclude your local `.venv`, `node_modules`, `dist`, `.git` and `.env`.
2. Click **Run**. The committed `.replit` selects Python 3.12 and Node.js 22, installs the locked npm packages and builds React, then installs the Python dependencies and starts FastAPI. The first install takes longer because it includes OCR models. Check the preview and `/health`.
3. Open **Publishing → Adjust settings** and select **Reserved VM**, running as a web server. Use a single server. Profiles currently live in process memory; multiple servers can lose track of the active session. They also expire after an hour and are cleared on restart/redeploy.
4. Confirm the settings below and publish. Then test the public URL with **Try sample**, skill confirmation, and role exploration. Deployment and genuine Replit usage proof must be completed in the team's account.

| Setting | Value |
|---|---|
| Runtime | Python 3.12 + Node.js 22.12 or newer |
| Build command | Use the committed `.replit` build command: npm install/build, then Python dependency installation |
| Run command | `.venv/bin/python -m src.main` |
| Internal / external port | `8000` / `80` |
| Environment | `PORT=8000` (already in `.replit`); no required API secrets |

`.replit` already includes the build/run commands and port mapping. `replit.nix` supplies the native C++ and zlib runtime libraries used by the OCR/PDF dependencies. Keep `PORT` and the internal port mapping consistent if you change them. The build installs into `.venv` so it does not write into the system Python installation. Development tools and the optional RunPod SDK are excluded from the web deployment; the latter has its own `runpod/requirements.txt`.

This remains one server deployment: Python serves both the built React frontend and `/api/v2`, using one public URL and port. Node is needed at build time; a second production server, CORS settings and a separate frontend host are unnecessary. The single-server choice follows the app's current session design. See Replit's [configuration reference](https://docs.replit.com/features/project-setup/configuration) and [deployment types](https://docs.replit.com/features/publishing/deployment-types). Source-backed evidence and verified course coverage remain separate team tasks described above.

## Tests

```bash
python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run build
python -m unittest discover -s tests -v
```

The ordinary suite includes real local OCR checks. Browser tests are opt-in. Install Chromium with `python -m playwright install chromium`, set `RUN_BROWSER_TESTS=1`, then run `python -m unittest discover -s tests -p test_browser.py -v`. Alternatively, set `BROWSER_CHANNEL=msedge` to use installed Microsoft Edge. Browser tests launch and stop their own server; `BROWSER_ARTIFACT_DIR` optionally saves screenshots outside the source tree.

## Replit and RunPod compliance

**Replit — required:** the team must actually use Replit and include verifiable proof in its technical/tools declaration, from its own account/project. Add the corresponding evidence to `submission/` after use.

**RunPod — conditional:** if model training, fine-tuning or inference **needs a GPU**, run those workloads on RunPod and include genuine account/Pod GPU/runtime evidence or actual serverless endpoint proof. The starter ZIP's RunPod demo handler and “proof” PDF are **not proof of real use**. If architecture is CPU/managed API only, document that and confirm interpretation with organizers if necessary.

## Submission plan

- Preliminary submission via **sdchack.my by 25 Oct 2026 07:59:59 MYT**.
- Official six items: completed official-form PRD PDF, pitch slides, functional prototype link, technical/tools declaration, public compliant GitHub repo, 5–7 minute YouTube demo.
- Repo must be newly created **after competition start**, have authentic commit history, contain Apache 2.0 `LICENSE`, be public for judging, and be frozen at deadline unless authorized.
- Actual proposal form: `submission/Submission Template SDC Hackathon.pdf`; working response draft: [`docs/PRELIMINARY_PROPOSAL_DRAFT.md`](docs/PRELIMINARY_PROPOSAL_DRAFT.md).

## Compliance and provenance

The **Terms & Conditions control conflicts**. The Participant Handbook provides operational requirements; the Official Handbook and sponsor brief are supplementary. Only synthetic demo CVs; dated citations for observed claims; clear hypothetical labels; no fictional course providers/jobs/statistics shown as real; declare tools, datasets, models, licenses and any pre-existing work.

## License

The repository will include the **Apache License 2.0** as required by the Participant Handbook. Third-party materials retain their own terms; verify the team has the right to release each file publicly.

## Current status

- [x] Technical specification drafted
- [x] Proposal-form answer draft prepared, with unresolved details explicitly marked
- [ ] Registered team data and URLs filled
- [ ] Public/legal data source selection validated
- [x] Fictional CV fixtures and working local application built
- [ ] Real source evidence, courses and measured evaluation completed
- [ ] Replit used and actual proof captured
- [ ] RunPod used **if** a GPU task is performed, with actual proof
- [ ] Six official preliminary items submitted through portal

CV recommendations use a blend of distinctive skill alignment and general requirement coverage. See [the matching formula and sample-CV acceptance results](docs/CV_MATCHING.md).

CV assessment validates canonical IDs against the database before and after AI,
and supplies skill kinds and definitions to the model. Matching v5 includes a
transparent comparison of estimated general-skill proficiency with available
O*NET required levels. See [the formula](docs/CV_MATCHING.md),
[CV formats](data/synthetic/profiles/cvs/domain_examples/README.md) and
[composition/styling checks](data/synthetic/profiles/cvs/layout_examples/README.md).

Every matched skill uses job-relative level suitability. Software level estimates are derived from documented occupational skill proxies and labelled separately from published general-skill requirements. Missing proxy ratings remain unknown.
