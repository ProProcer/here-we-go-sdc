"""Reproduce coverage statistics and synthetic scoring sensitivity, offline."""

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from src.ingestion.coverage import CoverageIndex
from src.ingestion.onet import CATALOG_FILE, ROOT, load_onet_catalog, write_json
from src.schemas.onet import CoveragePolicy

SAMPLE_CODES = [
    "15-2051.01",
    "15-1252.00",
    "13-2011.00",
    "29-1141.00",
    "47-2111.00",
    "43-4051.00",
]


def run_experiments(catalog):
    index = CoverageIndex(catalog)
    names = {s.skill_id: s.label for s in catalog.taxonomy.skills}
    groups = {g.group_id: g.label for g in catalog.taxonomy.software_groups}
    samples, sensitivity, invariant_checks = [], [], Counter()
    all_supported = set(names)
    for role in catalog.roles:
        rid = role.role_id
        required = index.general[rid]
        general = [
            r.skill_id
            for r in sorted(required, key=lambda r: (-r.importance, r.skill_id))
        ]
        demanded = sorted({r.skill_id for r in index.software[rid] if r.in_demand})
        empty = index.score(rid, [])
        full = index.score(rid, all_supported)
        if empty.score != 0 or full.score != 100:
            raise AssertionError(f"Boundary coverage failed: {rid}")
        invariant_checks["empty_and_full_boundary_roles"] += 1
        prefix = set()
        previous = 0.0
        # Exercise mixed general and software claims, including alternative examples.
        candidates = general + sorted({r.skill_id for r in index.software[rid]})
        for skill in candidates:
            prefix.add(skill)
            current = index.score(rid, prefix).score
            if current + 1e-6 < previous:
                raise AssertionError(f"Non-monotonic coverage: {rid}")
            previous = current
            invariant_checks["monotonic_additions"] += 1
        if not demanded:
            partial = general[: len(general) // 2]
            left = index.score(rid, partial, CoveragePolicy(general_share=0.25))
            right = index.score(rid, partial, CoveragePolicy(general_share=0.75))
            if left.score != right.score or left.software_coverage is not None:
                raise AssertionError("Absent software category changed the score")
            invariant_checks["missing_software_fallback_roles"] += 1
        if role.occupation_code not in SAMPLE_CODES:
            continue
        associations = index.software[rid]
        top = sorted(required, key=lambda r: (-r.importance, r.skill_id))[:5]
        samples.append(
            {
                "occupation_code": role.occupation_code,
                "title": role.role_title,
                "general_count": len(required),
                "software_count": len(associations),
                "in_demand_count": len(demanded),
                "top_general": [
                    {
                        "skill": names[r.skill_id],
                        "source_importance": r.source_importance,
                    }
                    for r in top
                ],
                "in_demand_software": [names[s] for s in demanded],
                "categories": sorted({groups[r.group_id] for r in associations}),
            }
        )
        profiles = {
            "general_only": set(general),
            "software_only": set(demanded),
            "half_general_half_software": set(general[::2] + demanded[::2]),
        }
        for label, available in profiles.items():
            scores = []
            for general_share in [0.25, 0.5, 0.75]:
                for group_share in [0.25, 0.5, 0.75]:
                    result = index.score(
                        rid,
                        available,
                        CoveragePolicy(
                            general_share=general_share, group_share=group_share
                        ),
                    )
                    scores.append(
                        {
                            "general_share": general_share,
                            "group_share": group_share,
                            "score": result.score,
                        }
                    )
            sensitivity.append(
                {
                    "role": role.role_title,
                    "synthetic_profile": label,
                    "minimum": min(s["score"] for s in scores),
                    "maximum": max(s["score"] for s in scores),
                    "scores": scores,
                }
            )
    # A real catalog category allows Java to support familiarity without granting Python.
    developer = next(r for r in catalog.roles if r.occupation_code == "15-1252.00")
    java = index.score(developer.role_id, ["skill:java"])
    if "skill:python" in java.matched_software_skill_ids:
        raise AssertionError("Java incorrectly granted exact Python coverage")
    if not java.group_matches:
        raise AssertionError("Java provided no category familiarity")
    invariant_checks["no_false_exact_tool_equivalence"] += 1
    raw_weight_share = []
    for role in catalog.roles:
        total_general = sum(r.importance for r in index.general[role.role_id])
        total_software = len(index.software[role.role_id])
        raw_weight_share.append(total_software / (total_general + total_software))
    return {
        "method": "purposive_six_occupation_sample_and_full_catalog_structural_checks",
        "catalog_fingerprint": hashlib.sha256(
            catalog.model_dump_json().encode()
        ).hexdigest(),
        "sample_is_representative": False,
        "profiles_are_synthetic": True,
        "no_hiring_or_transfer_calibration": True,
        "policy_decision": "Use equal group/exact and equal general/software shares as explicit provisional defaults; sensitivity does not identify optimal weights.",
        "flat_pool_software_share_if_every_example_weight_one": {
            "min": min(raw_weight_share),
            "median": statistics.median(raw_weight_share),
            "max": max(raw_weight_share),
        },
        "invariants_passed": dict(invariant_checks),
        "sample": samples,
        "sensitivity": sensitivity,
        "limitations": [
            "Synthetic profiles test behavior, not predictive accuracy.",
            "Group familiarity is not validated transfer or demonstrated task capability.",
            "No proficiency level is inferred or compared to O*NET Level.",
            "Equal shares remain adjustable by Person 2 after independent reviewed-profile evaluation.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG_FILE)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/experiments/onet/31.0/results.json"
    )
    args = parser.parse_args()
    report = run_experiments(load_onet_catalog(args.catalog))
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "invariants": report["invariants_passed"],
                "policy": report["policy_decision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
