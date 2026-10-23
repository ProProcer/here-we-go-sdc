# CV matching formula

Matches and roadmaps now use `reviewed_onet_fit_v5`. This version rewards agreement
between the profile's proficiency and the occupation's required level, rather
than adding the same proficiency multiplier to every relevant occupation.

## Level evidence

Only confirmed or explicitly self-reported database skills enter scoring.
For general skills, unsuppressed O*NET source levels are used directly. The
profile's beginner/intermediate/advanced estimate is mapped to 2/4/6 on the 0–7
scale as an explicit application proxy, not an official equivalence.
[O*NET scale definitions](https://www.onetonline.org/help/online/scales).

O*NET software examples do not contain direct required proficiency levels. The
following category rules produce clearly labelled estimates from the same
occupation's related general-skill rating:

| Software category | Related occupational skill |
| --- | --- |
| Database/query, development environments, GUI, object/component and web development | Programming |
| Spreadsheets and analytical/scientific software | Mathematics |
| CAD and CAD/CAM | Operations Analysis |
| Medical software | Monitoring |

A usable related source level up to 2 produces an estimated beginner band (2),
over 2 through 4 an intermediate band (4), and over 4 an advanced band (6).
For a tool in several mapped categories, the highest available estimated band
is used. These are product inference rules, not measured tool requirements.
The breakdown preserves `requirement_basis`, the proxy skill and its original
source rating. Missing, zero or suppressed proxy ratings are not filled in.
Unmapped categories show requirement unknown. In particular, a suppressed
Programming rating cannot create a Python requirement estimate.

## Suitability

Let p be the profile's 2/4/6 proficiency proxy and r the available required level.

    underqualified: Q = (p / r)^2
    meets/exceeds:  Q = 1 / (1 + 0.35 * (p - r) / 2)
    level_factor = 0.2 + 0.8 * Q

Matching the required level gives full suitability. A shortfall is penalized
more than surplus skill. An advanced person can still perform beginner work,
but a role matching their level receives higher alignment, all else equal.
The 20% floor retains limited presence credit rather than interpreting a level
mismatch as an absent skill. Unknown profile proficiency receives that floor.
Where the job requirement is unavailable, the factor is 0.2 + 0.3 times the prior
profile-level strength (0.6/0.8/1 for beginner/intermediate/advanced). It remains
below a known exact match and does not imply an invented required level.

## Combined score

For skill s, df(s) counts distinct occupations listing it. Its role affinity is
source general-skill importance, 1 for an exact in-demand software example, 0.5
for another exact software example, or 0 without a catalog connection.

    w(s) = 1 + ln((occupation_count + 1) / (df(s) + 1))
    A = sum(w(s) * role_affinity(s) * level_factor(s)) / sum(w(s))
    F = sum(importance * general_requirement_fulfilment) / sum(all general importance)
    skills_score = 0.65 * A + 0.35 * F
    breadth = min(1, supported_skill_count / 4)
    fit = 100 * breadth * ((1 - interest_share) * skills_score + interest_share * interests)

F measures capability separately from suitability: min(1, p / source_required)
for assessed general skills. Surplus skill still fulfils a requirement even if
it is a less close level match. Missing required general levels use presence
only, with unavailable status. Unknown profile levels receive no F proficiency
credit when a required level is available. An empty profile scores zero.

Recognized occupation-title, alias or family interests receive a 10% share;
otherwise the share is zero. A selected target is pinned without a score boost.
Sorting uses unrounded scores, then role ID. The alignment denominator is
independent of proficiency so level differences cannot cancel out for one skill.
`CoveragePolicy.profile_alignment_share` configures the 65/35 blend. Separate
software coverage diagnostics do not treat every alternative tool as mandatory.

All formula constants, proxy rules and skill-level crosswalks are transparent
application assumptions. Scores are exploratory, not empirically calibrated
hiring probabilities or education/licensing checks. The UI shows original
source ratings separately from estimates and labels the estimates explicitly.

## Python acceptance matrix

For a confirmed Python-only profile, no interests and the same one-skill breadth
reduction, the actual catalog yields:

| Profile level | Energy Auditors (beginner estimate) | Business Intelligence Analysts (intermediate estimate) | Computer Programmers (advanced estimate) |
| --- | --- | --- | --- |
| Beginner | 16.25 | 6.50 | 4.69 |
| Intermediate | 12.88 | 16.25 | 9.03 |
| Advanced | 10.90 | 12.88 | 16.25 |

The software estimates come from the occupations' Programming ratings of 0.75,
2.50 and 4.88 respectively, mapped to the bands above. A Python-only profile is
insufficient evidence of overall job eligibility. Tests check the crossover,
unknown/suppressed ratings, API revision updates, and changing recommended roles
through the real browser flow. CV extraction/layout invariance is unchanged.
The fictional sample still surfaces data occupations without target-role boosts.
Historical v2/v3/v4 test scores should not be compared directly with v5.
