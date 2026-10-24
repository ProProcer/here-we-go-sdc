# Preliminary Proposal — Working Draft Matched to Official PDF Form

> **Not the official submission PDF.** Transfer finalized answers into `submission/Submission Template SDC Hackathon.pdf` and export **one** PDF titled `SDC2026_TeamName_Preliminary.pdf`. Do not submit this Markdown in place of the required form. Bracketed items need team verification. Word limits are noted below.
>
> Uses original form sequence and labels. No completed form, attendance, experimental result or deployed feature is claimed here.

## 1. Team & Project Overview

| Form field | Planned entry / action |
|---|---|
| Team Name | `[REGISTERED TEAM NAME]` |
| Selected Domain | `Domain 1 — The Aiversecity Future-Ready Workforce Domain` |
| Selected SDG Track (1–17) | `SDG 4 — Quality Education` (also addresses relevant SDG 8 targets) |
| Project / Solution Name | `FutureReady AI` (working name) |
| Name (Leader) | `[REGISTERED TEAM LEADER]` |
| Email & Phone (Leader) | `[OFFICIAL CONTACT DETAILS — add only in submitted PDF, not public README]` |
| University Affiliation(s) | `[REGISTERED MEMBER UNIVERSITIES]` |
| Number of Team Members | `[NUMBER 1–5]` |

## 2. Executive Summary & Problem Statement

### 2.1 The Problem Context — maximum 250 words

AI is changing the tasks workers perform and the skills employers request. Yet students and early-career workers often make career choices using fragmented job descriptions, generalized AI predictions, and static course lists. A person may have useful transferable skills but cannot easily see which adjacent roles fit them, what specific skills are missing, or whether claims about AI-driven job changes are backed by dated evidence. Training options further vary in cost, prerequisites and quality.

We focus on Malaysian fresh graduates and early-career professionals navigating technology, data and business career pathways. The immediate challenge is not to predict exact job losses: it is to support better-informed career decisions under uncertainty, with clear evidence and accessible learning steps. The proposed solution aligns primarily with SDG Target 4.4, which concerns relevant technical and vocational skills for employment, and supports SDG 8.2/8.5 through career-relevant upskilling. We will validate claims about local training gaps against their original sources before citing precise figures.

### 2.2 The Proposed AI Solution — maximum 300 words

FutureReady AI is a Replit-hosted career exploration dashboard that transforms a synthetic CV or structured form into an editable skill profile. It maps skills to a normalized taxonomy and ranks standardized occupations with an explainable personal fit score and explicit missing skills. A separate updatable evidence layer tracks dated job-posting, AI-news and research signals, highlighting how AI may automate or augment tasks without presenting speculation as guaranteed job loss.

Users can open a role to inspect the current evidence-based outlook, then compare it with transparently labeled moderate and rapid AI-disruption stress tests. Scenario assumptions can change the priorities in a personalized learning plan while preserving the original observed facts. A constrained research and course-selection workflow recommends verified free or inexpensive learning resources, orders prerequisites, estimates time and cost where supported, and explains each role/skill's relevance to SDG targets.

The technical prototype will use Python/FastAPI, structured AI outputs, a normalized job-role dataset, source provenance, and an interactive dashboard deployed through Replit. If our chosen inference or embedding workload genuinely needs a GPU, it will run on RunPod and we will supply real proof. The system is a human decision-support tool, not a hiring or employment forecast engine. The live proof of concept will show one synthetic profile, ranked roles, dated signals and a visibly changing pathway across scenarios.

## 3. Technical Architecture & Implementation Plan

### 3.1 Conceptual Tech Stack

| Layer | Planned stack and role |
|---|---|
| UI | FastAPI + Jinja2/HTMX, CSS, optional Plotly; role explorer and scenario comparison |
| Back end | Python + FastAPI; Pydantic validation and pipeline orchestration |
| Data | SQLite, small licensed public job sample, standardized role and skill taxonomy, dated source records |
| AI | Configurable structured-output LLM for skill extraction and evidence summarization; exact name/API TBD |
| Matching | Deterministic weighted skill coverage and documented transferability rules |
| Trend/scenario | Updatable source records, task-level signal interpretation, deterministic synthetic stress-test engine |
| Learning resources | Verified course catalog with optional bounded research agent |
| Hosting | Replit **mandatory**; genuine proof after use |
| GPU | RunPod **only when chosen model/workload requires GPU**; proof if used |
| Documentation | GitHub README, Apache-2.0 license, traceable commits and declared third-party usage |

**System diagram:** Synthetic CV/form → validated skills → canonical role matching ← job/occupation database. Independently, dated AI/job signals → role/task outlook. Both feed an interactive dashboard; user selects role + scenario → gap-prioritized verified courses → ordered pathway + SDG mapping. See `docs/PROJECT_SPECIFICATION.md` for diagram and contracts.

**Sponsor-provided platform/GenAI used:** `[FILL AFTER ACTUAL USE: Replit project URL and purpose; RunPod proof if GPU used; name any actual sponsor GenAI API with task]`. Do not check “yes” for unutilized resources.

### 3.2 Design-Thinking & Deployment Strategy — maximum 200 words

**Empathize/define:** We narrowed the broad workforce problem to a fresh graduate asking, “Which realistic career should I prepare for, and what should I learn next?” Interviews or usability checks, if conducted, will be reported accurately, with no real CVs included in the judged demonstration. **Ideate:** We prioritized explainable fit and adaptable task-level AI evidence over a generic chatbot. **Prototype:** The team will integrate separate intake, role data, trend/scenario, reskilling and UI modules through typed JSON contracts. **Test:** Synthetic profiles and a curated role/course set will support repeatable skill-extraction, ranking, citation-validity, affordability and scenario-reversibility checks. **Deploy:** Replit will host a live interactive build with a cached fallback for external API failures. Each factual trend/course claim will include source information, and any unsupported result will be labeled unknown. Phase 2 would expand source coverage, improve evaluation and usability, and refine recommendations based on actual tests.

## 4. Preliminary Environmental & SDG Impact Framework

**Important:** The official form expects **numeric** values. The cells below are intentionally *not fabricated*. Replace bracketed baseline and target with a genuinely measured outcome before submitting. Do not use an invented percentage just to fill the form.

| Metric Category | Proposed draft content |
|---|---|
| Target SDG Sub-Target(s) | **4.4**: increase relevant technical/vocational skills for employment; supporting **8.2/8.5** |
| Current Problem Baseline | External context: Domain 1 brief cites **26%** formal AI training among Malaysian professionals (attributing it to Hays 2025); primary source verification required. **Prototype benchmark baseline:** `[MEASURE minutes / % verified pathway coverage using same synthetic cases with a static baseline workflow]`. |
| Core Measurable KPI | **% of synthetic test profiles for which the app yields a source-verified pathway covering the top 3 prioritized skill gaps in ≤5 minutes**. Report numerator, denominator and sample size. Secondary: % validated course links and evidence-backed trend claims. |
| Phase 2 Impact Target | **Proposed** at least **80%** of evaluation synthetic profiles meeting the above KPI. This is a *target*, not an achieved result; adjust after baseline evaluation. |

## 5. Eligibility & Readiness Checklist

- [ ] Every registered member completed any **mandatory** GenAI, Database and Cloud Deployment workshops required by the official form; check organizer attendance records instead of guessing.
- [ ] Problem statement and proposed measurable impact mapped explicitly to SDG 4.4 and relevant additional targets.
- [ ] Functional Replit-hosted prototype accessible via a real link (not a mockup alone).
- [ ] All fields filled in the original PDF form, within limits.

## 6. IP & Originality Declaration

### 6.1 Pre-Existing / Prior-Owned Work

**Yes/No:** `[DETERMINE TRUTHFULLY WITH EVERY MEMBER]`.

If yes, list only actual components and owners. The official **GitHub submission starter** is a permitted foundation but not an independently created project; **do not reuse its `.git/` history**. Obtain organizer clarification/approval for any significant prior materials if needed. The team must create the actual competition project after event commencement.

### 6.2 Third-Party Code, Datasets, or Models

**Yes/No:** `[LIKELY YES IF IMPLEMENTED; CONFIRM ACTUAL USAGE]`.

| Name (actual version/provider) | Type | License / allowed terms | Used where |
|---|---|---|---|
| FastAPI | Framework | `[verify installed/version licensing]` | API |
| Pydantic | Library | `[verify]` | Schemas |
| Pandas | Library | `[verify]` | ETL |
| `[ACTUAL JOB DATASET]` | Dataset | `[verify]` | Roles |
| `[ACTUAL LLM / AI PROVIDER]` | Model/API | `[provider terms]` | Extraction / summaries |
| `[ACTUAL COURSE SOURCES]` | External resource | `[source terms]` | Pathway |
| Replit | Cloud/dev | `[service terms]` | Hosting/development |
| RunPod | Cloud/GPU | `[service terms — only if used]` | GPU workload |

### 6.3 Employment-Related IP Conflicts

**Yes/No:** `[EACH TEAM MEMBER MUST CHECK OWN EMPLOYMENT/INTERNSHIP/CONSULTING AGREEMENTS]`; describe real agreement if applicable. Do not infer or auto-check.

## 7. Declaration

Signature: `[REGISTERED LEADER SIGNS OFFICIAL PDF]`  
Date: `[ACTUAL SUBMISSION DATE]`

---

## Additional submission items — not part of this single PDF form

The Participant Handbook requires **six** preliminary deliverables via the official portal by **25 October 2026, 07:59:59 MYT**: (1) this completed official-form PRD as PDF, (2) pitch deck, (3) functional prototype link, (4) technical/tools declaration including Replit proof and RunPod proof if used, (5) public compliant GitHub repository link, and (6) **5–7 minute YouTube pitching/demo video**.

The README and this planning draft supplement—not replace—those items. The original PDF's prescribed filename and word limits prevail over project documentation choices.
