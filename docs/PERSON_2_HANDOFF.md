# Person 2: typed profiles and weighted matching

Steps 1–6 are implemented as offline Python services. These are proposed v0.1.0
integration contracts for Persons 4 and 5 to review, not a record of their approval.
Person 1's catalog, taxonomy and importance weights are unchanged. All profiles
and role requirements in this example are synthetic.

## Theory and scoring policy

The pipeline is typed skill entries -> canonical skills -> editable profile ->
weighted coverage -> ranked matches and gaps. Exact taxonomy lookup handles
aliases without guessing additional skills. A complete form entry must be a
canonical ID, label or alias. This is not free-text CV extraction: a sentence
such as "No Python experience" will not be interpreted as Python knowledge.

Proficiency and confirmation are independent. Typed skills are self-reported,
with level unknown by default. Human review can set level explicitly, confirm a
claim, remove a skill or add a skill with supporting evidence. Evidence is stored
for explanation; the matcher never mines evidence prose for scoring features.
Confirmed does not imply independently certified proficiency.

Coverage is 1 for a self-reported or confirmed skill and 0 for an absent or
unverified skill. Unknown proficiency does not reduce coverage. This assesses
documented skill presence, not mastery. Person 1 does not yet supply required
proficiency levels, so inventing proficiency comparisons would be unsupported.

```
earned_weight = sum(importance for covered requirements)
total_weight = sum(importance for all role requirements)
coverage = earned_weight / total_weight
fit_score = round_half_up(100 * coverage, 2 decimal places)
```

For Data Analyst, Python (0.7) and SQL (0.9) earn 1.6 of 3.8: 42.11/100.
Statistics, visualization and communication remain unconfirmed gaps. This is
not a hiring probability. Missing evidence does not establish inability.

This milestone uses 100% required-skill coverage. The specification's proposed
70/20/10 formula is deferred until transferability and preference rules exist.
Those components are null, not fabricated zeros. Interests and desired role do
not affect scores. There is no AI-outlook or scenario input to personal fit.

Rank by unrounded Decimal coverage descending, then role ID ascending. Display
scores use two decimals and ROUND_HALF_UP; distinct underlying scores can have
the same displayed value. Zero total weight produces zero with a warning.
Every role is returned. manually_selected marks preference only; top-N pinning
and UI positioning remain future integration work.

## Code blocks and their purposes

### src/schemas/profile.py

- ProfileSkill: canonical skill ID/label, bounded level and confirmation choices,
  and nonempty supporting evidence. Its validator rejects blank evidence.
- ProfileConstraints: optional nonnegative budget and weekly time in (0,168].
- SkillsProfile: synthetic ID, reviewed skills, desired role, interests,
  constraints and warnings. Its validator rejects duplicate skill IDs.
- SkillContribution: each role requirement's weight, binary coverage, earned
  contribution, evidence and explanatory reason. Used for both matches and gaps.
- ScoreBreakdown: exposes numerator, denominator and ratio, method version,
  and explicitly unimplemented transferability/preferences.
- RoleMatch: role/sector identity, rank, score, breakdown, matched/missing
  requirements, synthetic provenance, selection flag and warnings.

All inherit Contract(extra="forbid"). Unsupported fields, including demographic
fields, are rejected. Interests are metadata only. The scorer reads only skill
IDs and confirmation, plus catalog requirements; level and evidence text never
become hidden ranking features. These contracts are stricter than the planning
examples: evidence is a list, and matched skills carry detailed contributions.

### src/profiles/skill_normalizer.py

- normalize_key: Unicode NFKC normalization, case folding and whitespace folding
  make equivalent typed names resolve consistently.
- skill_index: indexes canonical IDs, labels and aliases from Person 1. Rejects
  aliases assigned to different skills rather than choosing arbitrarily.
- normalize_entries: exact lookup, merges repeated aliases into one canonical
  skill, retains original entries for evidence, sorts by ID and returns unknown
  entries separately. Repetition cannot increase matching credit.

### src/profiles/intake.py

- validate_profile: checks skill IDs, canonical labels and optional desired role
  against the current catalog. Schema shape checks alone cannot establish these
  cross-file references.
- create_profile: converts explicit typed entries to self-reported profile skills,
  keeps proficiency unknown, reports unsupported entries and validates references.
- review_profile: accepts the complete replacement skill list, revalidates all
  fields/references, and returns a new profile. It supports additions, removals,
  evidence/level edits and confirmation changes without mutating the original.
  Unsupported-entry warnings remain as intake provenance; rebuilding typed input
  via create_profile regenerates them.

### src/profiles/matching.py

- Input preparation: validates the profile again and builds lookup tables for
  profile skills, taxonomy labels and sector labels.
- Role loop: evaluates every catalog role using its own requirement denominator.
- Requirement loop: assigns coverage from confirmation status, accumulates Decimal
  weights and creates the contribution/reason for matched or missing output.
- Result construction: exposes ratio, rounded score, synthetic and missing-data
  caveats, and desired-role metadata. Zero-weight and empty profiles are explicit.
- Final sorting: uses unrounded coverage and role ID, then assigns sequential
  ranks. No network, random state, current time or model output affects results.

### Fixtures, examples and tests

- data/synthetic/profiles/typed_inputs.json: five fictional typed inputs, manually
  specified expected skill IDs and expected role order (analytics, business,
  support, empty and duplicate-alias examples). These are not PDF/CV fixtures.
- src/profiles/demo.py: runs all fixtures through intake and matching, returning
  JSON-compatible profile/match pairs. Its CLI prints without modifying files.
- data/demo/person_2_responses.json: generated complete responses for Person 5.
- tests/test_profiles.py: fixture expectations, independently calculated weights,
  aliases/duplicates, add/remove/confirm review, missing inputs, invalid contracts,
  protected-field rejection, metadata independence, zero weights, deterministic
  ties, alias ambiguity and fixture/response consistency.

## Usage

From the repository root, with Python 3.10+ and pydantic==2.12.3 installed:

```python
from src.profiles.intake import create_profile, review_profile
from src.profiles.matching import match_roles

profile = create_profile("synthetic:example", ["Python3", "SQL"])
matches = match_roles(profile)
response = {"profile": profile.model_dump(mode="json"),
            "matches": [row.model_dump(mode="json") for row in matches]}

edited = [skill.model_dump() for skill in profile.skills]
edited[0]["confirmation"] = "confirmed"
profile = review_profile(profile, edited)
```

An already edited full profile payload can also be loaded with
SkillsProfile.model_validate(payload), then passed to match_roles, which checks
catalog references. This supports editing interests/constraints and desired role.
Invalid payloads raise Pydantic ValidationError; unknown catalog references raise
ValueError. Person 5 should translate these into appropriate API validation errors.

```powershell
.venv/Scripts/python -m src.profiles.demo
.venv/Scripts/python -m unittest discover -s tests -v
```

On another environment, including Replit, use its installed Python executable
instead of the Windows .venv path. This change does not establish Replit use.

## Remaining work

No PDF/plain-text CV parser, OCR, automatic free-text extraction, HTTP routes,
review screen, persistence, transferability scoring, preference scoring or top-N
pinning is added. Person 5 owns UI/routes; Person 4 can join missing_skills by
skill_id and importance. Broader vocabulary needs coordinated taxonomy additions.
Future extracted claims should start unverified and be reviewed before coverage.
