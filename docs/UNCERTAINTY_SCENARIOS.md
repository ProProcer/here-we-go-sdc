# Handling uncertainty: alternative career futures

The learning roadmap opens on the current occupational baseline, with moderate
and rapid adoption available from a scenario dropdown. It answers: **How would preparation
change if reliable AI assistance spread gradually or rapidly in this career?**

The scenarios share an illustrative three-year horizon. They have no estimated
probabilities and make no predictions of job loss, salary or local hiring demand.
Stories are never presented as news, source findings or future announcements.

## User experience

The compact **Choose your planning scenario** panel contains:

- A sourced baseline: O*NET occupational context and its release date.
- A Baseline/Moderate/Rapid dropdown; only the selected scenario is shown.
  Future stories include assumptions, actual career tasks, possible workflow
  changes and human responsibilities.
- Different practice activities and factors that could change adoption.
- An expandable baseline/moderate/rapid comparison of controlled learning-priority weights.
- Preparation useful across both assumed futures, including for people who
  already confirmed those skills.
- Scenario selection applies to the existing roadmap; selecting Baseline restores it.
- Separate, dated research background where a generated story used a real feed
  article. Such research does not verify a future outcome.

Every scenario is labelled hypothetical. AI-generated stories additionally show
their creation date and lack of human review. Application-authored illustrations
are labelled accurately and are always available without a model or network.
The selected complete illustration remains visible while an optional AI update
runs or fails. Baseline reads do not trigger AI generation. Comparison controls
use a flex layout with an explicit gap so show-all and baseline actions do not
run together on desktop or mobile.

## Calculations and AI responsibilities

`src/intelligence/scenarios.py` remains the numeric authority. Its existing
bounded, reversible adjustments feed the roadmap. The general moderate policy
adds 0.08 to selected checking, learning and communication priorities; rapid adds
0.16, capped at 1.00. Business Intelligence Analysts retains its specific authored
policy. These weights are illustrative application assumptions, not calibrated
employment predictions. The comparison table shows scenario-only weights before
any separately approved research adjustments.

`src/intelligence/futures.py` supplies complete occupation-specific illustrations
and caches optional AI explanations. A single bounded model request generates
both stories together from actual task IDs, priority skills, authored assumptions
and available research excerpts. AI does not set weights or change profiles,
personal fit, source evidence or course records. Switching scenarios requires no
new AI generation; the existing planner recalculates the selected roadmap.

Validation requires both distinct scenarios, actual supplied occupational tasks
and priority skills, known research references, conditional narratives, and
nonblank explanations. Numerical claims, probabilities, certainty language and
announcement claims are rejected. These checks limit malformed output; they do
not establish the plausibility of every statement. Generated narratives remain
explicitly hypothetical and unreviewed.

The private cache is `.trend-cache/futures.json`, keyed by occupation and catalog
version. A previous valid pair remains available during the next day's refresh.
Failed generations do not replace it. A maximum of one optional update runs at
a time, with a 35-second provider budget and a five-minute failure cooldown.

## Interfaces and verification

- `GET /api/v2/roles/{role_id}/futures` always returns a complete available pair.
  With a valid session it may request a background AI enhancement.
- `POST /api/v2/roles/{role_id}/futures/refresh` requires a valid session and
  requests new story text; it does not refetch news or alter numeric policy.
- `tests/test_futures.py` verifies offline availability, validation, cache
  recovery, source dates and separation from scoring and scenario calculations.
- `tests/test_web_app.py` checks public reads, session requirements and role IDs.
- The browser scenario journey verifies both stories, the comparison, applying
  scenarios, baseline restoration and unchanged personal fit.
