"""Fetch current sources, optionally interpret a role and export a small seed."""

import argparse
import json

from src.ingestion.selection import real_catalog
from src.intelligence.live_trends import LiveTrendService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-id", default="role:onet_15_2051_01")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--export-snapshot", action="store_true")
    args = parser.parse_args()
    service = LiveTrendService(real_catalog())
    try:
        print(json.dumps(service.refresh()), flush=True)
        if args.analyze:
            rows = service.analyze_role(args.role_id)
            print(json.dumps({"role_id": args.role_id, "supported_interpretations": len(rows)}), flush=True)
        if args.export_snapshot:
            service.export_seed()
            print("Saved source provenance and bounded supporting excerpts.", flush=True)
        result = service.for_role(args.role_id)
        print(json.dumps({"source_titles": [a["title"] for a in result["articles"]],
            "analysis_status": result["analysis_status"], "provider": result["analysis_provider"]}), flush=True)
    finally:
        service.close()


if __name__ == "__main__":
    main()
