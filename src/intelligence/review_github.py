"""Download trusted review artifacts without forwarding GitHub authentication."""

import io
import json
import zipfile
from pathlib import PurePosixPath
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.configure_role3_actions import API, api, credential
from src.intelligence.feeds import RejectRedirects

MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
ROOT_FILES = {
    "queue.json",
    "REVIEW_BRIEF.md",
    "SKILL_REVIEW_BRIEF.md",
    "skill_jobs.json",
    "skill_index.json",
    "ROLE_REVIEW_BRIEF.md",
    "role_jobs.json",
}
DIRECTORIES = {"ai_reviews", "findings", "skill_assessments", "role_assessments"}


class ArtifactRedirect(HTTPRedirectHandler):
    """Expose GitHub's signed redirect as HTTPError; never follow it with auth."""

    def redirect_request(self, *args, **kwargs):
        return None


def unpack_review_artifact(raw):
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError("The review download exceeds the local app's size limit")
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 12000 or sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise ValueError("The review archive exceeds the local app's size limit")
        for info in entries:
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or ":" in info.filename
                or len(path.parts) > 2
                or (info.external_attr >> 16) & 0o170000 == 0o120000
                or info.file_size > 4 * 1024 * 1024
            ):
                raise ValueError("The review archive contains an unsafe file reference")
            allowed = (
                len(path.parts) == 1
                and path.name in ROOT_FILES
                or len(path.parts) == 2
                and path.parts[0] in DIRECTORIES
                and path.suffix == ".json"
            )
            if not allowed or path.as_posix() in files:
                raise ValueError("The review archive contains an unexpected file")
            data = archive.read(info)
            if path.suffix == ".json":
                json.loads(data)
            else:
                data.decode("utf-8")
            files[path.as_posix()] = data
    if "queue.json" not in files:
        raise ValueError("The review archive has no review queue")
    return files


def latest_review_artifact():
    token = credential()  # Existing exact-repository Git credential, in memory only.
    runs = api(
        token,
        "/actions/workflows/role3-discovery.yml/runs?branch=main&status=completed&per_page=5",
    )["workflow_runs"]
    for run in runs:
        artifacts = api(token, f"/actions/runs/{run['id']}/artifacts")["artifacts"]
        artifact = next(
            (
                a
                for a in artifacts
                if a["name"] == "role3-discovery-state" and not a["expired"]
            ),
            None,
        )
        if artifact is None:
            continue
        request = Request(
            API + f"/actions/artifacts/{artifact['id']}/zip",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            build_opener(ArtifactRedirect()).open(request, timeout=30)
            raise ValueError("GitHub did not provide the expected artifact download")
        except HTTPError as error:
            if error.code != 302:
                raise ValueError(
                    f"GitHub artifact request failed (HTTP {error.code})"
                ) from None
            location = error.headers["Location"]
        parts = urlsplit(location)
        host = parts.hostname or ""
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or not host.endswith((".blob.core.windows.net", ".githubusercontent.com"))
        ):
            raise ValueError("GitHub returned an unexpected artifact download host")
        try:
            # New request: the GitHub credential is NEVER sent to the blob host.
            with build_opener(RejectRedirects()).open(
                Request(location), timeout=30
            ) as response:
                raw = response.read(MAX_DOWNLOAD + 1)
        except OSError:
            raise ValueError(
                "The saved GitHub report could not be downloaded; try again"
            ) from None
        return unpack_review_artifact(raw), {
            "run_id": run["id"],
            "url": run["html_url"],
            "conclusion": run["conclusion"],
            "updated_at": run["updated_at"],
        }
    raise ValueError("No retained review report was found in the latest completed runs")
