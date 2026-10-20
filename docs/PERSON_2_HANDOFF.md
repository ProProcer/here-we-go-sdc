# Person 2: typed profiles and weighted matching

The implemented Python services provide typed-skill intake, canonical skill
normalization, editable profiles, explainable role matching, fictional CV
parsing, transferability and preference scoring, and target-role pinning.
See [matching and CV intake](PERSON_2_MATCHING_AND_CV_INTAKE.md) for the detailed
scoring policy, parser limits and integration examples. The contracts are
proposals for Persons 4 and 5 to review, not a record of their approval.
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
readiness = coverage + partial_transfer_weight / total_weight
fit_score = round_half_up(100 * readiness, 2 decimal places)  # Without recognized interests
```

For Data Analyst without recognized interests, Python (0.7) and SQL (0.9)
earn 1.6 of 3.8: 42.11/100.
Statistics, visualization and communication remain unconfirmed gaps. This is
not a hiring probability. Missing evidence does not establish inability.

Matching combines direct coverage with bounded partial transfer credit. Related
reviewed skills can contribute 25% of an uncovered requirement's importance
through a shared catalog task, without repeating direct credit. The target
requirement remains a gap. Recognized explicitly entered interests receive 10%
of the final score; otherwise readiness receives 100%. AI outlook and scenario
assumptions do not enter personal fit. Zero total requirement weight produces
zero with a warning.

Results are ranked by unrounded Decimal fit descending, then role ID ascending.
Displayed scores use two decimals and ROUND_HALF_UP. Every role is returned by
default. With top_n, an excluded desired role is appended with pinned=true and
its original score and rank. manually_selected marks the user's choice.

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
  readiness, transferability, preferences and component weights.
- RoleMatch: role/sector identity, rank, score, breakdown, matched/missing
  requirements, transfer explanations, matched interests, synthetic provenance,
  selection/pinning flags and warnings.

All inherit Contract(extra="forbid"). Unsupported fields, including demographic
fields, are rejected. Only explicitly entered recognized interests affect
preference alignment. Skill IDs, confirmation and catalog requirements determine
readiness; level and evidence text never
become hidden ranking features. These contracts are stricter than the planning
examples: evidence is a list, and matched skills carry detailed contributions.

- TransferContribution: source skill, target requirement, shared task, partial
  credit, evidence and explanation for each transfer contribution.

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

- create_profile_from_cv: parses fictional PDF/plain-text documents and proposes
  unverified skills with evidence for human review. Parser and extraction details
  are documented in [matching and CV intake](PERSON_2_MATCHING_AND_CV_INTAKE.md).

### src/profiles/matching.py

- Input preparation: validates the profile again and builds lookup tables for
  profile skills, taxonomy labels and sector labels.
- Role loop: evaluates every catalog role using its own requirement denominator.
- Requirement loop: assigns coverage from confirmation status, accumulates Decimal
  weights and creates the contribution/reason for matched or missing output.
- Result construction: combines direct coverage, partial transfer credit and
  optional interest alignment; exposes component weights, evidence, rounded score,
  synthetic and missing-data caveats, and desired-role metadata.
- Final sorting and selection: uses unrounded fit and role ID, assigns ranks,
  and appends a selected target outside top_n without changing its rank or score.
  No network, random state, current time or model output affects results.

### Fixtures, examples and tests

- data/synthetic/profiles/typed_inputs.json: five fictional typed inputs, manually
  specified expected skill IDs and expected role order (analytics, business,
  support, empty and duplicate-alias examples).
- data/synthetic/profiles/cvs: three fictional text CVs and an analytics PDF.
- tests/test_cv_pipeline.py: document parsing, review-gated matching, protected
  attribute exclusion, transfer credit, preference handling and target pinning.
- src/profiles/demo.py: runs all fixtures through intake and matching, returning
  JSON-compatible profile/match pairs. Its CLI prints without modifying files.
- data/demo/person_2_responses.json: generated complete responses for Person 5.
- tests/test_profiles.py: fixture expectations, independently calculated weights,
  aliases/duplicates, add/remove/confirm review, missing inputs, invalid contracts,
  protected-field rejection, metadata independence, zero weights, deterministic
  ties, alias ambiguity and fixture/response consistency.

## Usage

From the repository root, with Python 3.10+ and requirements.txt installed:

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

HTTP routes, the review screen, persistence, actual Replit execution and
consumer approval of the proposed contracts remain outstanding. Person 5 owns
UI/routes; Person 4 can join missing_skills by skill_id and importance. Broader
vocabulary needs coordinated taxonomy additions. OCR is unsupported. Extracted
CV claims start unverified and must be reviewed before receiving skill coverage.
