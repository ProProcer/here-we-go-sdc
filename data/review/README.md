# Candidate findings awaiting review

`candidates/` contains AI-generated proposals, not accepted trend evidence.
Do not feed these JSON files directly to the evidence refresh command. Their
schema deliberately does not match `ReviewedSource` or `EvidenceLedger`.

The live Gemini extraction recorded on 2026-10-20 produced three findings from
the approved January 2026 Anthropic report. Exact quoted snippets and passage
references were checked automatically. Source text was parsed in memory; raw
HTML and complete article passages are not saved here.

Review each candidate against the report and its referenced section. Check the
entire paraphrase, the study period, geographic/sample scope, limitations and
whether a finding is observed, estimated or projected. Matching a short quotation
does not establish that the whole candidate is supported.

## Review notes for the first live run

File: `anthropic_economic_index_2026_01_20261020T151240188007Z_76a1792fdf83.json`.

- The coding-concentration finding describes platform use, not hiring demand.
- The productivity finding is labeled `author_projection`; retain that distinction.
- The geographic-usage candidate's generated limitation refers to "employment
  effects." Its finding is about a usage association, so that wording needs
  correction before acceptance. No causal employment effect is established.
- Study-period values were returned as unknown. The report contains sample-date
  information; review applicability before adding dates. The extractor never
  substitutes the publication date for missing study dates.

All three remain `pending_review`. An owner can now use the explicit
[approval CLI](../../docs/ROLE_3_APPROVAL.md) to prepare a plan and approve checked
wording, limitations and classification without hand-editing JSON. A separately
reviewed task interpretation is optional. The extraction records stay immutable;
reviewed definitions and snapshots record acceptance. There is no automatic approval.

## Saved run provenance and portability

These records retain their original timestamps, fingerprints, and review status.
Some audit fields contain the original Windows workspace path. Those paths are
provenance, not portable configuration: on another checkout, generate a fresh
candidate and approval plan rather than editing fingerprint-bound history.
Keys and full source articles are not included. The approved Anthropic finding
is in the accepted ledger; the DS-STAR plan remains prepared and its findings
are not admitted. See [the research review](research/README.md) for that follow-up.
