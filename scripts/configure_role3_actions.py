"""Configure/inspect this repository's Actions using existing Git credentials.

uv run --no-project --with pynacl python -m scripts.configure_role3_actions --configure-secret
python -m scripts.configure_role3_actions --status --sha COMMIT
Tokens and the Gemini key stay in memory and are never printed or written to disk.
"""

import argparse
import base64
import json
import os
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPOSITORY = "ProProcer/here-we-go-sdc"
API = "https://api.github.com/repos/" + REPOSITORY


def credential():
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if remote != "https://github.com/" + REPOSITORY + ".git":
        raise ValueError("Run this only in the intended repository")
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
        check=False,
    )
    values = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    if result.returncode or not values.get("password"):
        raise ValueError("Existing GitHub Git credential unavailable")
    return values["password"]


def api(token, path, *, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "FutureReadyAI-role3-setup",
        },
    )
    with urlopen(request, timeout=30) as response:
        data = response.read()
    return json.loads(data) if data else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure-secret", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--sha")
    args = parser.parse_args()
    token = credential()
    if args.configure_secret:
        secrets = api(token, "/actions/secrets")
        if any(s["name"] == "GEMINI_API_KEY" for s in secrets["secrets"]):
            print(
                "Repository GEMINI_API_KEY already configured; preserved existing secret."
            )
        else:
            from nacl.public import PublicKey, SealedBox

            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise ValueError("Local Gemini key is not configured")
            public = api(token, "/actions/secrets/public-key")
            encrypted = SealedBox(PublicKey(base64.b64decode(public["key"]))).encrypt(
                key.encode()
            )
            api(
                token,
                "/actions/secrets/GEMINI_API_KEY",
                method="PUT",
                payload={
                    "encrypted_value": base64.b64encode(encrypted).decode(),
                    "key_id": public["key_id"],
                },
            )
            print("Configured encrypted repository GEMINI_API_KEY.")
    if args.status:
        workflow = api(token, "/actions/workflows/role3-discovery.yml")
        print(json.dumps({k: workflow[k] for k in ("id", "name", "state", "html_url")}))
        path = "/actions/workflows/role3-discovery.yml/runs?per_page=5"
        if args.sha:
            if not all(c in "0123456789abcdef" for c in args.sha.lower()):
                raise ValueError("Invalid commit SHA")
            path += "&head_sha=" + args.sha
        runs = api(token, path)["workflow_runs"]
        print(
            json.dumps(
                [
                    {
                        k: r[k]
                        for k in ("id", "status", "conclusion", "html_url", "head_sha")
                    }
                    for r in runs
                ]
            )
        )


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(
            f"GitHub Actions request failed with HTTP {error.code}; no credential values were logged."
        ) from None
