# O*NET® 31.0 source snapshot

These eight CSVs are the original downloaded files. `manifest.json` records
their row counts, SHA-256 fingerprints and official data dictionary URLs.
Verification date: 2026-10-21. The original download date was not recorded and
is explicitly unknown. This release was published in August 2026; individual
records can be much older.

Source: [O*NET 31.0 Database](https://www.onetcenter.org/database.html),
U.S. Department of Labor, Employment and Training Administration (USDOL/ETA).
The database content is used under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
See the [official database license](https://www.onetcenter.org/license_db.html).
The repository's Apache-2.0 code license does not replace this data license.
O*NET® is a trademark of USDOL/ETA.

FutureReady AI transforms these data through coverage filtering, identifier
mapping, importance rescaling, and explicit withholding of irrelevant or
suppressed records. USDOL/ETA has not approved, endorsed or tested these
modifications. Generated output retains source attribution and limitations.

Rebuild from the repository root:

```bash
python -m src.ingestion.onet
python -m src.ingestion.onet_experiments
python -m src.ingestion.onet_demo
```

See [the Person 1 handoff](../../../../docs/PERSON_1_HANDOFF.md) for the
contract, decisions, experiments and migration responsibilities.
