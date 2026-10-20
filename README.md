# FutureReady AI — Aiversecity Future-Ready Workforce

> **Planning-stage project** for SDC Hackathon 2026, Domain 1. No functional build or real deployment is represented by this repository planning pack.  
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

## Tech stack (proposed, not yet deployed)

| Layer | Proposed technology |
|---|---|
| UI | Jinja2/HTMX + CSS (optional Plotly) |
| Application | Python / FastAPI / Pydantic |
| Data | Pandas + SQLite + JSON snapshots |
| Matching | Taxonomy normalization, deterministic scoring, optional CPU-friendly semantic embeddings |
| AI | To-be-declared structured-output LLM, with source validation |
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
src/main.py                   # Future FastAPI entry point
src/{ingestion,profiles,intelligence,reskilling,api,schemas}/
runpod/handler.py             # Optional actual GPU inference code
src/templates/ + src/static/  # Web UI
data/{raw,processed,synthetic,demo}/
tests/                       # Regression and integration tests
docs/PROJECT_SPECIFICATION.md
docs/PRELIMINARY_PROPOSAL_DRAFT.md
submission/Submission Template SDC Hackathon.pdf  # ORIGINAL blank official PDF
```

This is a design tree. Only some planning files exist yet. **No provided sample code counts as a working prototype.**

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
usage and the proposed `GET /api/roles` adapter. This is a module handoff; the
complete app is still to be implemented.

## How to run (once implementation exists)

This planning pack has **no runnable app yet**. After actual implementation, replace these instructions with tested commands for the committed `requirements.txt` and `.replit` config; expected target:

```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

On Replit, configure the actual app launch command, ports and required Secrets. Add the real working deployment link and verified setup details here. **Never place secrets in the repository.**

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
- [ ] Synthetic profile fixtures and working implementation built
- [ ] Real source evidence, courses and measured evaluation completed
- [ ] Replit used and actual proof captured
- [ ] RunPod used **if** a GPU task is performed, with actual proof
- [ ] Six official preliminary items submitted through portal
