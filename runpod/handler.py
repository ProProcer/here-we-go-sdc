"""RunPod serverless handler.

Deploy this file as a RunPod Serverless Endpoint.
Replace the placeholder logic with your model inference.
"""

import runpod


def handler(job: dict) -> dict:
    prompt = job["input"].get("prompt", "")
    # TODO: load your model and run inference here
    return {"output": f"Echo: {prompt}"}


runpod.serverless.start({"handler": handler})
