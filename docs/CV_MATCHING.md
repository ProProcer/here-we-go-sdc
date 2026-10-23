# CV matching formula

The real-catalog matcher now reports `reviewed_onet_fit_v4` in matches and roadmaps.
This replaces the original grouped-coverage ranking. The synthetic demo matcher
has its own existing contract.

## Formula

Only confirmed or explicitly self-reported skills enter the score. Extracted,
unverified claims never enter the score. Let P be that set and N the occupation
count in the loaded catalog.

For skill s, count the distinct occupations listing it as a general requirement
or software example, df(s). Repeated associations in software categories count once.

    distinctiveness(s) = 1 + ln((N + 1) / (df(s) + 1))

The role affinity is its source general-skill importance, 1 for an exact in-demand
software example, 0.5 for another exact software example, and 0 for no connection.
When a tool occurs in multiple categories, use its highest affinity once.

    L(s) = 0.4 if unknown, 0.6 if beginner, 0.8 if intermediate, 1.0 if advanced
    A = sum(distinctiveness(s) * affinity(role, s) * L(s) for s in P)
        / sum(distinctiveness(s) for s in P)
    G = sum(importance of matched general requirements)
        / sum(importance of all general requirements)
    B = min(1, number of supported skills / 4)
    level_credit = min(1, profile_level_proxy / required_source_level)
    F = sum(importance * level_credit for confirmed general requirements)
        / sum(importance of all general requirements)
    skills_score = 0.65 * A + 0.35 * F
    fit = 100 * B * ((1 - p) * skills_score + p * I)

All skills, including software, receive level-sensitive alignment through L(s).
The denominator stays independent of level; normalizing by L(s) too would cancel
out the difference when the profile contains only one skill. L(s) is a transparent
application weight, not a claim about a job's required software proficiency.
The breakdown retains presence-only alignment separately for explanation.

A is zero for an empty profile. p is 0.10 when a recognized occupational title,
alias or family interest was supplied, otherwise zero. I is the fraction of those
recognized interests associated with this role. Without supported skills B is
zero, so interests alone cannot generate a match. Scores are rounded only for
display; sorting uses full precision, then role ID for deterministic ties.

`CoveragePolicy.profile_alignment_share` changes the 0.65 alignment weight; its
complement weights F. The existing `general_share` and `group_share` settings
still govern the separate grouped-coverage diagnostics, not the v4 fit formula.
This separates ranking from the number of software alternatives listed for a job.

## Why this changes the recommendations

The old formula rewarded a role listing Excel as its sole in-demand software
example with complete software coverage. Roles listing many alternative tools
received much less software coverage even when the CV included SQL, Python and
Tableau. The new alignment denominator is the person's supported skills, and
specialist skills receive higher weight than widely shared skills. General
requirements retain an importance-weighted fulfilment term using required levels. Category
familiarity remains visible, with no assumed equivalence between tools.

Profiles with one to three supported skills receive the explicit B reduction.
Four skills is an application assumption, as are the 65/35 blend and 0.5 contextual
software affinity. These are transparent exploratory weights, not an empirically
calibrated probability of employment. Education, licensing and seniority are not
eligibility checks. AI levels remain estimates. To make the comparison explicit, the application uses
beginner=2, intermediate=4, advanced=6 as approximate points on the 0–7 source
scale. This is a product assumption, not an official O*NET crosswalk. Unknown
profile levels receive presence alignment but no proficiency credit when the
job has a usable required level. A required level of zero needs no extra credit
threshold. Missing or suppressed required levels use presence only and are marked
unavailable. No required proficiency is fabricated for software examples.
The drawer shows the actual source level, the person's estimate, the proxy and
credit for each general skill. Increasing a person's level cannot reduce that
skill's credit; a higher job requirement cannot increase it.
See [O*NET's scale definitions](https://www.onetonline.org/help/online/scales).

The extractor also avoids claiming the catalog's scientific-methods skill from
the phrase "Computer Science" or "Data Science" alone. An explicit Science claim
still extracts normally. The authored sample CV itself is unchanged.

## Acceptance check

The actual downloadable sample PDF is parsed through normal intake and confirmed
without adding interests or a target role. The acceptance suite requires Data
Scientists first and relevant data occupations within the top ten; its numerical
fit changes with assessed proficiency. Earlier v2 scores were presence-only, and v3 adjusted only general requirement
fulfilment. V4 also adjusts every skill's alignment. Historical scores should not
be compared directly across these formula versions.

Previously Business Intelligence Analysts ranked 88th, while Ophthalmic Medical
Technicians ranked third. Those unrelated medical roles now fall outside the
top ten. `tests/test_cv_recommendations.py` covers the sample, a separate web
programming profile, sparse evidence, unverified claims, target pinning,
explanation arithmetic, and duplicate evidence. No sample-specific role boosts
or provider calls are used by matching.

The role drawer shows A, general presence, F, the required-level comparisons and the weights, the breadth reduction when applicable,
and each CV skill's contribution. Grouped software coverage remains visible as
separate context. The same match score flows into the learning roadmap.

## Python-only regression

For a confirmed profile containing only Python, Business Intelligence Analysts
now scores 9.75 at beginner, 13.00 at intermediate and 16.25 at advanced. Unknown
scores 6.50. The one-skill evidence-breadth reduction still applies. All catalog
occupations with a Python association respond monotonically to these level
changes; occupations without a Python association remain at zero. Tests cover
single-skill SQL, Excel and general skills too, plus live HTTP revision updates
and the actual browser level-editing flow. Software required-level fields remain
unavailable rather than inventing a measured job requirement.
