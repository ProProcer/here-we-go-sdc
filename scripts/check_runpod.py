"""Read RunPod endpoint metadata and account balance without running inference."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from src.config import load_local_environment
from src.intelligence.feeds import RejectRedirects


def main():
    load_local_environment()
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    endpoint = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
    if not key or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", endpoint):
        print("RunPod key or endpoint configuration is missing/invalid.")
        return 1
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
               "User-Agent": "ikiguy-configuration-check"}
    requests = [
        ("endpoint", Request(f"https://rest.runpod.io/v1/endpoints/{endpoint}", headers=headers)),
        ("available_endpoints", Request("https://rest.runpod.io/v1/endpoints", headers=headers)),
        ("balance", Request("https://api.runpod.io/graphql", headers=headers,
            data=json.dumps({"query": "query { myself { clientBalance } }"}).encode())),
    ]
    failed = False
    for label, request in requests:
        try:
            with build_opener(RejectRedirects()).open(request, timeout=20) as response:
                payload = json.loads(response.read(512 * 1024))
            if label == "endpoint":
                # Do not print endpoint environment variables or credentials.
                print(json.dumps({"check": label, "authenticated": True,
                    "name": payload.get("name"), "template_id": payload.get("templateId"),
                    "workers_min": payload.get("workersMin"), "workers_max": payload.get("workersMax")}))
            elif label == "available_endpoints":
                items = payload if isinstance(payload, list) else payload.get("endpoints", [])
                print(json.dumps({"check": label, "count": len(items),
                    "endpoints": [{"id": item.get("id"), "name": item.get("name"),
                                   "template_id": item.get("templateId")} for item in items]}))
            else:
                account = (payload.get("data") or {}).get("myself")
                if not isinstance(account, dict) or "clientBalance" not in account:
                    print(json.dumps({"check": label, "verified": False,
                        "reason": "Balance unavailable for this API key or query."}))
                    failed = True
                else:
                    print(json.dumps({"check": label, "verified": True,
                        "balance_usd": account["clientBalance"]}))
        except HTTPError as error:
            print(json.dumps({"check": label, "verified": False, "http_status": error.code}))
            failed = True
        except (OSError, URLError, ValueError):
            print(json.dumps({"check": label, "verified": False, "reason": "connection_failed"}))
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
