# Person 2: matching and CV intake

Current module handoff. Person 1's catalog and Person 3's outlooks are unchanged.
No HTTP routes, review screen or actual Replit execution are added. The v2 method
and additive response fields are proposals requiring consumer coordination.

## Explainable transferability and preferences

Direct skill coverage is C = earned_weight / total_weight.
Only self-reported/confirmed skills count. Unknown level remains independent.

Task-based transfer uses Person 1's task/skill relationships. A reviewed skill
that is NOT already a requirement of the target role can support an uncovered
requirement in the same role task. Each source can support at most one target;
each target receives at most one source. Stable skill/task ordering resolves
multiple candidates. Zero-weight targets do not earn transfer credit.

```
partial_transfer_weight = sum(target_importance * 0.25)
T = partial_transfer_weight / total_weight
readiness = C + T
```

The 25% amount is an authored illustrative assumption, not a measured competency
equivalence. Transfer targets remain missing_skills: partial credit establishes
neither possession nor proficiency. For example, Excel is not a Data Analyst
requirement in this fixture, but shares routine_reporting with visualization:
Excel alone earns 0.8 * 0.25 / 3.8 = 5.26/100. Python is already directly required
and cannot earn extra credit toward SQL. C + T cannot exceed 1 because direct and
transfer target sets are disjoint and transfer credit is capped at 25% per gap.

Preferences come exclusively from explicitly entered profile.interests. A small
versioned-in-code vocabulary maps analytics/data analysis/statistics to Data
Analyst; business/business analysis/requirements analysis to Business Analyst;
and IT support/technical support/troubleshooting to IT Support. Exact normalized
labels only; no CV-derived, demographic or target-role inference. Duplicate
interests count once. P is matching recognized interests / all recognized
interests. Unsupported interests are ignored and contribute no denominator.

```
recognized interests: fit = 100 * (0.90 * readiness + 0.10 * P)
no recognized interests: fit = 100 * readiness
```

An interest-only profile can receive preference points, with an empty-skill
warning; this does not assert skill readiness. Zero total requirement weight
always produces zero with a warning. Scores are rounded half-up to two decimals,
but sorting uses unrounded Decimal scores and then ascending role ID.

The planning specification's 70/20/10 draft is intentionally not adopted:
its independent transferability term lacks a defined baseline. Here transfer
adds bounded partial credit only to gaps, avoiding repeated direct credit and
allowing full coverage to reach 100 when preferences are absent/aligned. This
policy is explicit under score_breakdown.method = reviewed_fit_v2 and should be
reviewed with consumers before integration. It is a relative exploratory
heuristic, not a validated hiring probability. AI scenarios never enter fit.

Code blocks:

- preferences.py / ROLE_INTERESTS: inspectable role-interest vocabulary.
- preference_alignment: normalize/deduplicate input; return P and matched labels,
  or None when preference information is absent/unsupported.
- transferability.py / PARTIAL_CREDIT: explicit versioned policy constant.
- transferable_requirements: builds eligible sources and missing targets, joins
  through role tasks, prevents reuse and returns cited contribution records.
- matching.py / match_roles: retains direct requirement evaluation, adds C/T/P
  breakdown and readiness, calculates final fit and stable ranking.
- schemas/profile.py: ScoreBreakdown now includes transferability, preferences,
  readiness and component weights; TransferContribution records source, target,
  task, fraction, earned weight, evidence and explanation. RoleMatch adds
  transferable_skills, matched_interests and pinned. Existing profile schema
  remains compatible; old response snapshots have been regenerated.

## Pinned target-role treatment

match_roles(profile, top_n=N) returns the top N ranked roles plus the desired
role if it lies outside that set. The appended record has pinned=true and keeps
its original rank and score. Top N is a positive integer; invalid values raise
ValueError. A target already in the top N is not duplicated. Without top_n every
role is returned in score order. manually_selected marks the user's choice in
either case; pinned specifically means appended outside the cutoff.

The final selection block in match_roles handles this after scoring/ranking,
so preference for a job title cannot change suitability or displace a top-N role.
Person 5 should render rank as true fit rank and mark the appended target.

## Bounded PDF and plain-text CV intake

create_profile_from_cv(profile_id, content_bytes, filename) parses and proposes
skills for review. Only fictional demonstration documents should be supplied.

- cv_parser.py / constants: 2 MiB upload, five PDF pages, 50,000 extracted
  characters, 2 MiB decoded page stream, ten-second PDF worker timeout.
- CVParseError: stable code plus a typed-form fallback message. No raw CV or
  underlying parser exception is returned in errors.
- ParsedCV: transient page text and format, not persisted candidate data.
- _check_text: enforces length, nonempty text and rejects NUL binary content.
- parse_cv: checks size/extension, strictly decodes UTF-8(-BOM) text, verifies
  PDF header and invokes a child process. subprocess.run kills and waits for the
  child on timeout. Validates worker response and extracted text.
- pdf_worker.py / extract_pdf: rejects encryption, malformed PDFs, page excess,
  excessive decoded streams, excessive extracted text and documents with no
  readable text. Supports digital text PDFs, not OCR.
- pdf_worker.py / main: reads bounded input from stdin, returns bounded structured
  JSON and sanitized error codes. Parent discards stderr. Nothing is written to
  disk or logged by the parser.
- extraction.py / patterns: dictionary aliases with word boundaries, Unicode
  normalization and case-insensitive matching. Splits lines into clauses and
  skips conservative negative/aspirational clauses and labeled personal fields.
- extract_profile: merges mentions by skill ID, retains up to five evidence
  passages (500 characters each) with page/line positions, sets all claims
  unverified and levels unknown, and emits review warnings.
- intake.py / create_profile_from_cv: connects parser and extractor to the same
  profile contract used by typed input. review_profile remains the review gate.

Limits are operational safeguards, not a hard memory sandbox: decoded stream
length is checked after decompression. The worker can consume memory before
that check; a production deployment should apply process/container memory and
concurrency limits. The web adapter must also reject oversized uploads before
buffering. There is no OCR, encoding guessing, automatic proficiency inference,
semantic understanding or universal negation detection. Conservative extraction
can miss legitimate skills; human review and typed fallback are essential.
Multi-column PDF reading order and evidence line numbers may differ from visual
layout. pypdf cannot extract image-only text and warns that decoding streams can
use substantial memory: https://pypdf.readthedocs.io/en/stable/user/extract-text.html

## Tests, fixtures and usage

tests/test_cv_pipeline.py exercises real in-memory PDFs, text/PDF equivalence,
unverified-to-reviewed matching, fictional CV fixtures, negation and boundaries,
protected-field changes, similar CVs, byte/page/text limits, invalid/encrypted/
blank PDFs, encoding errors, timeout fallback, transfer gaps, preferences and
top-N pinning. The PDF builder creates synthetic documents using a standard
font and text stream; no real candidate content is used. Existing tests still
cover review edits, alias collisions, repeated runs, duplicates and tie ordering.

data/synthetic/profiles/cvs contains three fictional .txt CVs and an analytics
PDF. data/demo/person_2_responses.json contains updated complete typed responses.

```python
from src.profiles.intake import create_profile_from_cv, review_profile
from src.profiles.matching import match_roles

profile = create_profile_from_cv(
    "synthetic:example", b"Skills: Python3, SQL", "fictional.txt")
# UI presents evidence; confirm only after the human actually reviews it.
edits = [skill.model_dump() for skill in profile.skills]
# Following a user's explicit approval:
for skill in edits:
    skill["confirmation"] = "confirmed"
profile = review_profile(profile, edits)
matches = match_roles(profile, top_n=2)
```

The loop is demonstration code, not automatic confirmation behavior. Person 5
must collect actual review decisions. Import CVParseError for upload validation;
its code distinguishes fallback cases. Typed create_profile remains available.

```
python -m pip install -r requirements.txt
python -m src.profiles.demo
python -m unittest discover -s tests -v
```

The pinned PDF dependency is pypdf==6.21.1 (BSD-3-Clause); it performs local
CPU text extraction without an API key, LLM or GPU. Replit use and deployment
remain future work, as do UI/routes and consumer approval of proposed contracts.
