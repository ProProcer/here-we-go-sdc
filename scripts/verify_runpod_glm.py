"""Submit/check one synthetic GLM warm-up job without using Gemini backup."""

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from src.config import load_local_environment
from src.intelligence.feeds import RejectRedirects

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / ".role3-review/runpod-probe.json"


def api(path, *, payload=None):
    endpoint = os.environ["RUNPOD_ENDPOINT_ID"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", endpoint):
        raise ValueError("Invalid endpoint ID")
    request = Request(f"https://api.runpod.ai/v2/{endpoint}/" + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"],
                 "Content-Type": "application/json"},
        method="GET" if payload is None else "POST")
    with build_opener(RejectRedirects()).open(request, timeout=30) as response:
        return json.loads(response.read(512 * 1024))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--assessment", action="store_true", help="Verify all skills in the fictional sample CV")
    args = parser.parse_args()
    load_local_environment()
    receipt_path = RECEIPT.with_name("runpod-assessment-probe.json") if args.assessment else RECEIPT
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    if args.submit:
        if receipt.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            raise SystemExit("An existing verification job is still pending; check it before submitting another.")
        body = {"model": os.environ["RUNPOD_MODEL"],
                "messages": [{"role": "user", "content": 'Return exactly this JSON object: {"ok": true}'}],
                "max_tokens": 512, "temperature": 0, "stream": False,
                "response_format": {"type": "json_object"},
                "chat_template_kwargs": {"enable_thinking": False}}
        if args.assessment:
            from src.ingestion.selection import real_catalog
            from src.profiles.intake import create_profile_from_cv
            from src.profiles.samples import sample_cv_pdf
            from src.profiles.assessment import AssessmentBatch, INSTRUCTION, assessment_input, assessment_schema
            profile = create_profile_from_cv("synthetic:deployment_probe", sample_cv_pdf(),
                                             "sample.pdf", catalog=real_catalog())
            data = assessment_input(profile.skills)
            schema = assessment_schema(profile.skills)
            body.update(max_tokens=4096, messages=[
                {"role": "system", "content": INSTRUCTION + " Return JSON only, matching this schema: "
                    + json.dumps(schema)},
                {"role": "user", "content": json.dumps(data)},
            ])
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "AssessmentBatch", "strict": True, "schema": schema}}
        result = api("run", payload={"input": {"openai_route": "/v1/chat/completions", "openai_input": body},
            "policy": {"executionTimeout": 180000, "ttl": 600000}})
        receipt = {"endpoint_id": os.environ["RUNPOD_ENDPOINT_ID"], "job_id": result["id"],
                   "submitted_at": datetime.now(UTC).isoformat(), "status": result["status"]}
        if args.assessment:
            receipt["expected_skill_ids"] = [s.skill_id for s in profile.skills]
    elif args.cancel:
        result = api("cancel/" + receipt["job_id"], payload={})
        receipt["status"] = result.get("status", "CANCEL_REQUESTED")
    else:
        health = api("health")
        print(json.dumps({"health": health}))
        if not receipt.get("job_id"):
            return 0
        result = api("status/" + receipt["job_id"])
        receipt.update({key: result[key] for key in ("status", "delayTime", "executionTime", "workerId", "error", "output") if key in result})
        if result.get("status") == "COMPLETED":
            outputs = result.get("output", [])
            completion = outputs[-1] if isinstance(outputs, list) and outputs else outputs
            try:
                choice = completion["choices"][0]
                if args.assessment:
                    from src.profiles.assessment import AssessmentBatch
                    batch = AssessmentBatch.model_validate_json(choice["message"]["content"])
                    correct_content = (len(batch.skills) == len(receipt["expected_skill_ids"])
                                       and {s.skill_id for s in batch.skills} == set(receipt["expected_skill_ids"]))
                else:
                    correct_content = json.loads(choice["message"]["content"]) == {"ok": True}
                valid = (completion["model"] == os.environ["RUNPOD_MODEL"]
                         and choice["finish_reason"] == "stop" and correct_content)
            except (KeyError, IndexError, TypeError, ValueError):
                valid = False
            receipt["inference_verified"] = valid
            if valid:
                deployment_path = ROOT / ".role3-review/runpod-deployment.json"
                deployment = json.loads(deployment_path.read_text())
                deployment.update(inference_verified=True, verified_at=datetime.now(UTC).isoformat(),
                    verification_job_id=receipt["job_id"], returned_model=completion["model"])
                if args.assessment:
                    deployment["full_assessment_verified"] = True
                    deployment["assessed_skill_count"] = len(batch.skills)
                deployment_path.write_text(json.dumps(deployment, indent=2) + "\n", encoding="utf-8")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    return int(receipt.get("status") in {"FAILED", "TIMED_OUT", "CANCELLED"}
               or receipt.get("inference_verified") is False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HTTPError as error:
        raise SystemExit(f"RunPod verification failed (HTTP {error.code}).") from None
