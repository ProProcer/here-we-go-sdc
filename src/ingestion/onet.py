"""Deterministic O*NET 31.0 ingestion. Run ``python -m src.ingestion.onet``."""

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.schemas.onet import OnetCatalog

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data/raw/onet/31.0"
DEFAULT_OUTPUT = ROOT / "data/processed/onet/31.0"
CATALOG_FILE = DEFAULT_OUTPUT / "catalog.json"
TABLES = {
    "occupation_data": {"O*NET-SOC Code", "Title", "Description"},
    "job_titles": {"O*NET-SOC Code", "Job Title", "Short Title"},
    "task_statements": {"O*NET-SOC Code", "Task ID", "Task", "Task Type", "Date"},
    "essential_skills": {
        "O*NET-SOC Code",
        "Element ID",
        "Element Name",
        "Scale ID",
        "Data Value",
        "Recommend Suppress",
        "Not Relevant",
        "Date",
    },
    "transferable_skills": {
        "O*NET-SOC Code",
        "Element ID",
        "Element Name",
        "Scale ID",
        "Data Value",
        "Recommend Suppress",
        "Not Relevant",
        "Date",
    },
    "software_skills": {
        "O*NET-SOC Code",
        "Workplace Example",
        "Element ID",
        "Element Name",
        "In Demand",
        "Hot Technology",
    },
    "content_model_reference": {"Element ID", "Element Name", "Description"},
    "scales_reference": {"Scale ID", "Scale Name", "Minimum", "Maximum"},
}
FAMILIES = {
    "11": "Management",
    "13": "Business and Financial Operations",
    "15": "Computer and Mathematical",
    "17": "Architecture and Engineering",
    "19": "Life, Physical, and Social Science",
    "21": "Community and Social Service",
    "23": "Legal",
    "25": "Educational Instruction and Library",
    "27": "Arts, Design, Entertainment, Sports, and Media",
    "29": "Healthcare Practitioners and Technical",
    "31": "Healthcare Support",
    "33": "Protective Service",
    "35": "Food Preparation and Serving Related",
    "37": "Building and Grounds Cleaning and Maintenance",
    "39": "Personal Care and Service",
    "41": "Sales and Related",
    "43": "Office and Administrative Support",
    "45": "Farming, Fishing, and Forestry",
    "47": "Construction and Extraction",
    "49": "Installation, Maintenance, and Repair",
    "51": "Production",
    "53": "Transportation and Material Moving",
    "55": "Military Specific",
}
# Exact labels/abbreviations only. These are not alternative-tool equivalences.
SOFTWARE_NAMES = {
    "python": ("skill:python", "Python", ["python3"]),
    "structured query language sql": (
        "skill:sql",
        "SQL",
        ["Structured query language SQL"],
    ),
    "microsoft excel": ("skill:microsoft_excel", "Microsoft Excel", ["Excel"]),
    "microsoft power bi": (
        "skill:microsoft_power_bi",
        "Microsoft Power BI",
        ["Power BI"],
    ),
    "oracle java": ("skill:java", "Java", ["Oracle Java"]),
}
LIMITATIONS = [
    "U.S. occupational descriptions and ratings; not verified Malaysian hiring demand.",
    "O*NET release freshness is distinct from individual record update months.",
    "General weights are source Importance / 5, not probabilities or proficiency thresholds.",
    "Software observations are examples, not requirements every worker must meet.",
    "In Demand is a binary occupation-specific signal, not a measured importance weight.",
    "Software categories support familiarity credit, not tool equivalence or assessed proficiency.",
    "Imported task-to-skill links are unavailable and remain empty; do not infer transfer from co-occurrence.",
    "Education, licensing, experience, knowledge, abilities and Job Zones are not eligibility checks in this catalog.",
    "The grouped coverage baseline is exploratory and has not been validated against hiring outcomes.",
]


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def identifier(prefix: str, value: str) -> str:
    return prefix + re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def software_identity(label: str) -> tuple[str, str, list[str]]:
    key = normalized(label)
    if key in SOFTWARE_NAMES:
        return SOFTWARE_NAMES[key]
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"skill:software_{digest}", label, []


def month(value: str) -> str:
    return datetime.strptime(value, "%m/%Y").strftime("%Y-%m")


def _unique(rows, key, table):
    result = {}
    for row in rows:
        value = key(row)
        if value in result:
            raise ValueError(f"Duplicate source key in {table}: {value}")
        result[value] = row
    return result


def read_inputs(raw: Path) -> tuple[dict, dict]:
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    tables = {}
    if manifest["release"] != "31.0":
        raise ValueError("Only pinned O*NET 31.0 inputs are supported")
    for name, required in TABLES.items():
        path = raw / f"{name}.csv"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = manifest["files"][path.name]
        if digest != expected["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f"Missing source columns: {path.name}")
            rows = list(reader)
        if len(rows) != expected["rows"]:
            raise ValueError(f"Source row-count mismatch: {path.name}")
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError(f"Malformed source rows: {path.name}")
        tables[name] = rows
    return tables, manifest


def build_onet_catalog(
    raw_directory: str | Path = DEFAULT_RAW,
) -> tuple[OnetCatalog, dict]:
    """Build a full real-data handoff and audit without modifying raw inputs."""
    tables, manifest = read_inputs(Path(raw_directory))
    occupations = _unique(
        tables["occupation_data"], lambda r: r["O*NET-SOC Code"], "occupation_data"
    )
    for name in [
        "job_titles",
        "task_statements",
        "essential_skills",
        "transferable_skills",
        "software_skills",
    ]:
        unknown = {r["O*NET-SOC Code"] for r in tables[name]} - occupations.keys()
        if unknown:
            raise ValueError(f"Unknown source occupation codes in {name}: {unknown}")
    _unique(tables["task_statements"], lambda r: r["Task ID"], "task_statements")
    reference = _unique(
        tables["content_model_reference"],
        lambda r: r["Element ID"],
        "content_model_reference",
    )
    scales = _unique(
        tables["scales_reference"], lambda r: r["Scale ID"], "scales_reference"
    )
    if (float(scales["IM"]["Minimum"]), float(scales["IM"]["Maximum"])) != (1, 5):
        raise ValueError("Unexpected Importance scale")
    if (float(scales["LV"]["Minimum"]), float(scales["LV"]["Maximum"])) != (0, 7):
        raise ValueError("Unexpected Level scale")
    present = {
        name: {r["O*NET-SOC Code"] for r in tables[name]}
        for name in TABLES
        if "O*NET-SOC Code" in TABLES[name]
    }
    eligible = set(occupations)
    reasons = {
        "task_statements": "missing_tasks",
        "essential_skills": "missing_essential_ratings",
        "transferable_skills": "missing_transferable_ratings",
        "software_skills": "missing_software_examples",
    }
    for name in reasons:
        eligible &= present[name]
    excluded = [
        {
            "occupation_code": code,
            "title": row["Title"],
            "reasons": [
                reason for name, reason in reasons.items() if code not in present[name]
            ],
        }
        for code, row in sorted(occupations.items())
        if code not in eligible
    ]
    role_id = {code: identifier("role:onet_", code) for code in eligible}
    skills, requirements = {}, []
    counts = Counter()
    latest = defaultdict(list)
    for name in ["essential_skills", "transferable_skills"]:
        records = _unique(
            tables[name],
            lambda r: (r["O*NET-SOC Code"], r["Element ID"], r["Scale ID"]),
            name,
        )
        for (code, element, scale), row in sorted(records.items()):
            if code not in eligible or scale != "IM":
                continue
            level = records.get((code, element, "LV"))
            if level is None or level["Not Relevant"] not in {"Y", "N"}:
                counts["unknown_relevance_excluded"] += 1
                continue
            if level["Not Relevant"] == "Y":
                counts["irrelevant_pairs_excluded"] += 1
                continue
            if row["Recommend Suppress"] != "N":
                counts["suppressed_or_unknown_importance_excluded"] += 1
                continue
            source_importance = float(row["Data Value"])
            suppressed = level["Recommend Suppress"] != "N"
            if suppressed:
                counts["suppressed_levels_withheld"] += 1
            skill_id = identifier("skill:onet_", element)
            definition = reference[element]
            skills[skill_id] = {
                "skill_id": skill_id,
                "label": row["Element Name"],
                "aliases": [],
                "kind": "general",
                "element_id": element,
                "description": definition["Description"],
            }
            updated = month(row["Date"])
            latest[code].append(updated)
            requirements.append(
                {
                    "role_id": role_id[code],
                    "skill_id": skill_id,
                    "importance": round(source_importance / 5, 6),
                    "source_importance": source_importance,
                    "source_level": None if suppressed else float(level["Data Value"]),
                    "level_suppressed": suppressed,
                    "updated_month": updated,
                    "evidence_ids": [f"source:onet_31_0_{name}"],
                }
            )
    if {r["role_id"] for r in requirements} != set(role_id.values()):
        raise ValueError("An eligible occupation has no usable general requirements")
    aliases = defaultdict(set)
    for row in tables["job_titles"]:
        code = row["O*NET-SOC Code"]
        aliases[code].update(
            v.strip() for v in [row["Job Title"], row["Short Title"]] if v.strip()
        )
    tasks, role_tasks = [], defaultdict(list)
    for row in tables["task_statements"]:
        code = row["O*NET-SOC Code"]
        if code not in eligible:
            continue
        tid = identifier("task:onet_", row["Task ID"])
        role_tasks[code].append(tid)
        updated = month(row["Date"])
        tasks.append(
            {
                "task_id": tid,
                "label": row["Task"],
                "source_task_id": row["Task ID"],
                "task_type": row["Task Type"],
                "source_updated_month": updated,
            }
        )
    associations = []
    groups = {}
    source_pairs = set()
    for row in sorted(
        tables["software_skills"],
        key=lambda r: (
            r["O*NET-SOC Code"],
            normalized(r["Workplace Example"]),
            r["Element ID"],
        ),
    ):
        code = row["O*NET-SOC Code"]
        if code not in eligible:
            continue
        if row["In Demand"] not in {"Y", "N"} or row["Hot Technology"] not in {
            "Y",
            "N",
        }:
            raise ValueError("Unknown software demand flag")
        sid, label, names = software_identity(row["Workplace Example"])
        key = (code, sid, row["Element ID"])
        if key in source_pairs:
            raise ValueError(f"Duplicate software observation: {key}")
        source_pairs.add(key)
        if sid in skills and normalized(skills[sid]["label"]) != normalized(label):
            raise ValueError("Software identity collision")
        skills[sid] = {
            "skill_id": sid,
            "label": label,
            "aliases": names,
            "kind": "software",
        }
        gid = identifier("group:onet_", row["Element ID"])
        group = groups.setdefault(
            gid,
            {
                "group_id": gid,
                "label": row["Element Name"],
                "element_id": row["Element ID"],
                "skill_ids": set(),
            },
        )
        group["skill_ids"].add(sid)
        associations.append(
            {
                "role_id": role_id[code],
                "skill_id": sid,
                "group_id": gid,
                "in_demand": row["In Demand"] == "Y",
                "hot_technology": row["Hot Technology"] == "Y",
                "evidence_ids": ["source:onet_31_0_software_skills"],
            }
        )
    roles = [
        {
            "role_id": role_id[code],
            "occupation_code": code,
            "role_title": occupations[code]["Title"],
            "description": occupations[code]["Description"],
            "aliases": sorted(aliases[code] - {occupations[code]["Title"]}),
            "family_id": f"family:soc_{code[:2]}",
            "task_ids": sorted(role_tasks[code]),
            "source_ids": [
                "source:onet_31_0_occupation_data",
                "source:onet_31_0_job_titles",
                "source:onet_31_0_task_statements",
            ],
            "latest_rating_month": max(latest[code]),
        }
        for code in sorted(eligible)
    ]
    provenance = {
        "verified_at": manifest["verified_at"],
        "downloaded_at": manifest["downloaded_at"],
        "attribution": "Contains adapted information from the O*NET 31.0 Database by USDOL/ETA, used under CC BY 4.0. O*NET is a trademark of USDOL/ETA. FutureReady AI modified the information; USDOL/ETA has not approved, endorsed, or tested these modifications.",
        "modifications": [
            "Coverage filtering and explicit exclusions",
            "Normalized identifiers and exact aliases",
            "Importance divided by 5; irrelevant pairs omitted; suppressed levels withheld",
            "SOC occupational families, not industry sectors",
            "Software categories exposed for familiarity, not equivalence",
            "Task-to-skill mappings left unasserted",
        ],
        "inputs": [
            {"filename": filename, **info}
            for filename, info in sorted(manifest["files"].items())
        ],
    }
    payload = {
        "provenance": provenance,
        "taxonomy": {
            "skills": [skills[k] for k in sorted(skills)],
            "tasks": sorted(tasks, key=lambda r: r["task_id"]),
            "occupational_families": [
                {"family_id": f"family:soc_{prefix}", "label": FAMILIES[prefix]}
                for prefix in sorted({c[:2] for c in eligible})
            ],
            "software_groups": [
                {**groups[k], "skill_ids": sorted(groups[k]["skill_ids"])}
                for k in sorted(groups)
            ],
        },
        "sources": [
            {
                "source_id": f"source:onet_31_0_{name}",
                "title": f"O*NET 31.0 {name.replace('_', ' ').title()}",
                "url": f"https://www.onetcenter.org/dictionary/31.0/csv/{name}.html",
                "license": "CC-BY-4.0",
            }
            for name in sorted(TABLES)
        ],
        "roles": roles,
        "role_skills": sorted(
            requirements, key=lambda r: (r["role_id"], r["skill_id"])
        ),
        "software_associations": sorted(
            associations, key=lambda r: (r["role_id"], r["skill_id"], r["group_id"])
        ),
        "excluded_occupations": excluded,
        "limitations": LIMITATIONS,
    }
    catalog = OnetCatalog.model_validate(payload)
    software_counts = Counter(r.role_id for r in catalog.software_associations)
    demand_counts = Counter(
        r.role_id for r in catalog.software_associations if r.in_demand
    )
    general_counts = Counter(r.role_id for r in catalog.role_skills)

    def distribution(counter):
        import statistics

        values = sorted(counter[r.role_id] for r in catalog.roles)
        return {
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
            "zero_occupations": values.count(0),
        }

    audit = {
        "release": "31.0",
        "input_occupations": len(occupations),
        "included_occupations": len(roles),
        "excluded_occupations": len(excluded),
        "general_requirements": len(requirements),
        "software_associations": len(associations),
        "tasks": len(tasks),
        "software_groups": len(groups),
        "filters": dict(sorted(counts.items())),
        "general_per_role": distribution(general_counts),
        "software_per_role": distribution(software_counts),
        "in_demand_per_role": distribution(demand_counts),
        "task_skill_mapping": "unavailable_not_inferred",
        "excluded": excluded,
    }
    return catalog, audit


def load_onet_catalog(path: str | Path = CATALOG_FILE) -> OnetCatalog:
    return OnetCatalog.model_validate_json(Path(path).read_text(encoding="utf-8"))


def get_onet_roles(path: str | Path = CATALOG_FILE) -> dict:
    """Explicit versioned response; does not replace the legacy get_roles()."""
    return load_onet_catalog(path).model_dump(mode="json")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    catalog, audit = build_onet_catalog(args.raw)
    write_json(args.output / "catalog.json", catalog.model_dump(mode="json"))
    write_json(args.output / "audit.json", audit)
    print(
        json.dumps({k: v for k, v in audit.items() if k not in {"excluded"}}, indent=2)
    )


if __name__ == "__main__":
    main()
