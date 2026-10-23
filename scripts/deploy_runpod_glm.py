"""Prepare/apply the reviewed scale-to-zero GLM endpoint; never print API keys."""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from src.config import load_local_environment
from src.intelligence.feeds import RejectRedirects

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "runpod/glm_deployment.json"
RECEIPT = ROOT / ".role3-review/runpod-deployment.json"


def api(path, *, method="GET", payload=None):
    request = Request("https://rest.runpod.io/v1" + path, method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"],
                 "Content-Type": "application/json", "User-Agent": "ikiguy-model-setup"})
    with build_opener(RejectRedirects()).open(request, timeout=30) as response:
        return json.loads(response.read(1024 * 1024))


def save_configuration(endpoint_id, model):
    path = ROOT / ".env"
    rows = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    updates = {"RUNPOD_ENDPOINT_ID": endpoint_id, "RUNPOD_MODEL": model,
               "LLM_PROVIDER": "runpod", "LLM_FALLBACK_PROVIDER": "gemini"}
    for name, value in updates.items():
        existing = next((i for i, row in enumerate(rows) if row.startswith(name + "=")), None)
        if existing is None:
            rows.append(name + "=" + value)
        else:
            rows[existing] = name + "=" + value
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not args.apply:
        print(json.dumps(manifest, indent=2))
        return 0
    load_local_environment()
    if not os.environ.get("RUNPOD_API_KEY", "").strip():
        raise SystemExit("RUNPOD_API_KEY is missing.")
    endpoint_spec = manifest["endpoint"]
    if endpoint_spec["workersMin"] != 0 or endpoint_spec["workersMax"] != 1:
        raise SystemExit("Expected zero minimum and one maximum worker.")
    endpoints = api("/endpoints")
    if not isinstance(endpoints, list):
        endpoints = endpoints.get("endpoints", [])
    existing = next((e for e in endpoints if e.get("name") == endpoint_spec["name"]), None)
    if existing:
        if existing.get("workersMin") != 0 or existing.get("workersMax") != 1:
            raise SystemExit("Existing named endpoint has different worker limits; inspect before reuse.")
        endpoint = existing
        print("Reusing the existing ikiguy GLM endpoint.", flush=True)
    else:
        template = api("/templates", method="POST", payload=manifest["template"])
        RECEIPT.parent.mkdir(exist_ok=True, parents=True)
        RECEIPT.write_text(json.dumps({"template_id": template["id"], "state": "template_created"}, indent=2))
        endpoint = api("/endpoints", method="POST", payload={**endpoint_spec, "templateId": template["id"]})
        print("Created the GLM endpoint with scale-to-zero and one maximum worker.", flush=True)
    receipt = {"endpoint_id": endpoint["id"], "template_id": endpoint.get("templateId"),
               "workers_min": endpoint["workersMin"], "workers_max": endpoint["workersMax"],
               "model": manifest["template"]["env"]["MODEL_NAME"], "inference_verified": False}
    RECEIPT.parent.mkdir(exist_ok=True, parents=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    save_configuration(endpoint["id"], receipt["model"])
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HTTPError as error:
        raise SystemExit(f"RunPod setup failed (HTTP {error.code}); inspect the local receipt before retrying.") from None
