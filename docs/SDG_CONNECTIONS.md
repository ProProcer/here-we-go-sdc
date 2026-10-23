# Role and individual-skill SDG connections

The selected career and every contextual skill have an explained, conditional
connection to at least one UN SDG target. The roadmap separates role application
from skill development, including skills already confirmed in the profile.

## Mapping policy

The original curated rules in `data/processed/onet/31.0/sdg_mappings.json` remain
in use. They cover employment-related skill development under Target 4.4 and
selected occupational applications in health, education, innovation and justice.
Their source links point to official UN target definitions.

`map_role_sdg_connections` now completes default real-catalog role coverage:

1. Use an applicable existing sector-specific role rule.
2. Otherwise, where an actual occupational task concerns data, analysis,
   technology, systems, processes, efficiency or productivity **and** the role
   requires an analytical skill, describe a conditional Target 8.2 opportunity.
   The explanation names that actual task. It requires a demonstrated improvement
   and does not infer economic impact from the occupation title alone.
3. Otherwise, link preparation/progression in that career to Target 4.4, with
   scope `career_preparation`. This is explicitly a learning-pathway connection,
   not an assertion about the social impact of every activity in that role.

These are transparent application rules, not UN-endorsed classifications or
observed SDG outcomes. Explicit caller-supplied rule sets continue to omit
unsupported mappings; default coverage does not override their restrictions.

## Skills and plans

The real-catalog plan has an optional `sdg_summary` alongside its existing
`sdg_connections`. The summary contains:

- Explained role links with goal names, targets, practical examples and conditions.
- One row per contextual skill with its canonical label and own target links.
- Profile/planned-learning/role-requirement/review status and role relevance.
- Coverage counts and a visible interpretation note.

The contextual skill set includes occupational general requirements, profile
skills, planned objectives, selected software and learning-step prerequisites.
Each skill receives its own applicable learning link; eligible work-application
links are also attached. A missing default learning tag for a known catalog skill
has an explicit Target 4.4 capability-development fallback. Unknown skill IDs
are rejected. Confirming a skill does not remove its mapping or imply a new gap.
Skills outside the selected occupation retain their learning links and are marked
as having no established role relevance.

Role and learning connections remain separate even if they share the same target.
The summary is exported with the plan. The public role-detail endpoint also
exposes its `sdg_connections`, so a career's link can be explored before planning.

## Interface and audiences

The roadmap's **How your pathway can contribute** section shows career context,
coverage counts, searchable skill rows, status filters and expandable examples.
The first six matching skills are shown with an explicit count and a show-all
action. Official UN source links, application conditions and the distinction
between a possible contribution and measured impact remain available.

Examples support adults adapting to changing work, fresh graduates demonstrating
capability, career switchers explaining transferable skills, and HR/L&D teams
agreeing development goals and supporting internal mobility. The mappings do not
classify people for redundancy or establish hiring suitability.

`tests/test_sdg_coverage.py` checks all 910 roles and baseline tags for all 8,687
catalog skills, confirmed-skill retention, source links, role scope and invalid
IDs. API and browser checks cover plan integration, individual skill links,
search/filter behaviour, scenario dropdowns and spacing between actions.
