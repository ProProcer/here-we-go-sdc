"""Private review-menu actions. Human clicks use the existing evidence gates."""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.ingestion.selection import real_catalog
from src.intelligence import role_evidence
from src.intelligence.discovery import (
    CONFIG,
    STATE,
    DiscoveryConfig,
    canonical_url,
    review_source,
)
from src.intelligence.discovery import (
    DECISIONS as SOURCE_DECISIONS,
)
from src.intelligence.gemini import DEFAULT_MODEL
from src.intelligence.review_github import latest_review_artifact
from src.intelligence.skill_evidence import (
    DECISIONS as MAPPING_DECISIONS,
)
from src.intelligence.skill_evidence import (
    active_assessments,
    approve_mapping,
    local_file,
    read_json,
    run_assessments,
)
from src.intelligence.source_review import (
    approve_review,
    effective_recommendation,
    fingerprint,
    run_reviews,
)
from src.intelligence.sources import DEFAULT_REGISTRY, load_registry
from src.intelligence.storage import atomic_json

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ReviewItem:
    key: str
    kind: str
    title: str
    skill: str
    status: str
    suggestion: str
    version: str
    details: str
    news_id: str
    skill_id: str | None = None
    mapping_sha256: str | None = None
    approvable: bool = False
    block_reason: str = ""
    url: str = ""
    role_id: str | None = None


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


class ReviewMenuService:
    def __init__(self, root=ROOT, *, state_directory=None, catalog=None, model=None):
        self.root = Path(root).resolve()
        self.directory = Path(
            state_directory or self.root / ".role3-review/state"
        ).resolve()
        if not self.directory.is_relative_to(self.root):
            raise ValueError("The local review state must stay inside this checkout")
        self.state_path = self.directory / "queue.json"
        self.manifest_path = self.directory.parent / "menu.json"
        self.sources_path = self.root / SOURCE_DECISIONS.relative_to(ROOT)
        self.mapping_path = self.root / MAPPING_DECISIONS.relative_to(ROOT)
        self.role_path = self.root / role_evidence.DECISIONS.relative_to(ROOT)
        self.registry_path = self.root / DEFAULT_REGISTRY.relative_to(ROOT)
        self.config_path = self.root / CONFIG.relative_to(ROOT)
        self.catalog = catalog
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    def manifest(self):
        return read_json(self.manifest_path, {"pending_paths": []})

    def _mark_pending(self, *paths):
        manifest = self.manifest()
        pending = set(manifest["pending_paths"])
        for path in paths:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(self.root):
                raise ValueError("Decision path escapes the checkout")
            pending.add(resolved.relative_to(self.root).as_posix())
        manifest["pending_paths"] = sorted(pending)
        atomic_json(self.manifest_path, manifest)

    def _seed(self):
        if self.state_path.exists():
            return
        canonical = self.root / STATE.relative_to(ROOT)
        queue = read_json(canonical, {"items": []})
        needed = {"queue.json", "REVIEW_BRIEF.md", "SKILL_REVIEW_BRIEF.md"}
        for row in queue["items"]:
            if row.get("ai_review_path"):
                needed.add(row["ai_review_path"])
                record = read_json(
                    local_file(canonical.parent, row["ai_review_path"]), {}
                )
                if record.get("candidate_path"):
                    needed.add(record["candidate_path"])
        needed |= {
            p.relative_to(canonical.parent).as_posix()
            for p in (canonical.parent / "skill_assessments").glob("*.json")
        }
        needed |= {
            p.relative_to(canonical.parent).as_posix()
            for p in (canonical.parent / "role_assessments").glob("*.json")
        }
        for reference in needed.copy():
            if reference.startswith(("skill_assessments/", "role_assessments/")):
                record = read_json(local_file(canonical.parent, reference), {})
                needed.add(record["source_review_path"])
        for reference in needed.copy():
            if reference.startswith("ai_reviews/"):
                record = read_json(local_file(canonical.parent, reference), {})
                if record.get("candidate_path"):
                    needed.add(record["candidate_path"])
        for reference in needed:
            source = local_file(canonical.parent, reference)
            if source.exists():
                atomic_bytes(local_file(self.directory, reference), source.read_bytes())
        if not self.state_path.exists():
            atomic_json(self.state_path, queue)

    def refresh(self, downloader=latest_review_artifact):
        if self.manifest()["pending_paths"]:
            raise ValueError(
                "Save your local decisions to GitHub before loading another report"
            )
        files, run = downloader()
        # Publish the new queue last, after all of its immutable references exist.
        for reference, body in files.items():
            if reference != "queue.json":
                atomic_bytes(local_file(self.directory, reference), body)
        atomic_bytes(self.state_path, files["queue.json"])
        manifest = self.manifest()
        manifest["run"] = run
        atomic_json(self.manifest_path, manifest)
        return self.snapshot()

    def _source_decisions(self):
        return {
            d["discovery_id"]: d
            for d in read_json(self.sources_path, {"decisions": []})["decisions"]
        }

    def _overlay_source_status(self):
        queue = read_json(self.state_path, {"items": []})
        decisions = self._source_decisions()
        registry = {
            str(s.source_url): s for s in load_registry(self.registry_path).sources
        }
        for row in queue["items"]:
            decision = decisions.get(row["discovery_id"])
            row["source_review_status"] = (
                decision["decision"] if decision else "pending_review"
            )
            source = registry.get(row["url"])
            if row["source_review_status"] == "approve" and (
                source is None
                or source.publisher != row["publisher"]
                or source.published_at.isoformat() != row["published_at"]
                or row.get("metadata_changed")
            ):
                row["source_review_status"] = "needs_re_review"
        atomic_json(self.state_path, queue)
        return queue, decisions

    def snapshot(self):
        self._seed()
        queue, decisions = self._overlay_source_status()
        items = []
        for row in queue["items"]:
            record = (
                read_json(local_file(self.directory, row["ai_review_path"]), {})
                if row.get("ai_review_path")
                else {}
            )
            digest = (
                hashlib.sha256(
                    local_file(self.directory, row["ai_review_path"]).read_bytes()
                ).hexdigest()
                if record
                else None
            )
            status = {"approve": "Approved", "reject": "Rejected"}.get(
                row["source_review_status"], "Needs review"
            )
            suggestion = (
                effective_recommendation(record) if record else "Awaiting AI review"
            )
            details = [
                row["title"],
                row["publisher"] + " · " + row["published_at"],
                "AI suggestion: " + suggestion.replace("_", " "),
                "",
            ]
            if record:
                details += [record["draft"]["summary"], "", "WHAT TO CHECK"]
                details += ["• " + c for c in record["draft"]["human_checks"]]
                details += ["• " + c for c in record["challenge"]["unresolved_issues"]]
                details += ["", "AI CHECKS"]
                details += [
                    f"{c['dimension']}: {c['status']} — {c['explanation']}"
                    for c in record["draft"]["checks"]
                ]
                details += ["", "FINDINGS"]
                for i, finding in enumerate(record["draft"]["findings"]):
                    verdict = (
                        "supported"
                        if i in record["supported_finding_indices"]
                        else "unverified / blocked"
                    )
                    details += [
                        f"• {finding['claim']} ({verdict}; {finding['evidence_type']})",
                        f"  Quote: “{finding['quote']}” — {finding['reference']['passage_id']}",
                    ]
                details += [
                    "",
                    "CROSS-SOURCE CHECK",
                    record["draft"]["cross_source_explanation"],
                ]
                details += [
                    "",
                    "Models: " + " / ".join(record["returned_models"]),
                    "Reviewed: " + record["reviewed_at"],
                    "Source: " + row["url"],
                    "",
                    "Approving this source does not approve its findings or change learning weights.",
                ]
                if record.get("grounding_error"):
                    details += [
                        "",
                        "Citation check failed: " + record["grounding_error"],
                    ]
            if row.get("ai_review_error"):
                details += [
                    "",
                    "Latest AI check failed. This is the previous review.",
                    row.get("ai_review_error_detail", row["ai_review_error"]),
                ]
            if row["discovery_id"] in decisions:
                decision = decisions[row["discovery_id"]]
                details += [
                    "",
                    f"Decision: {decision['decision']} · {decision['reviewer']}",
                    decision["reason"],
                ]
            block = "" if record else "Run an AI check before approving this source"
            if row.get("ai_review_error") or row.get("metadata_changed"):
                block = "Resolve the failed or changed source review before approval"
            version = fingerprint(
                {
                    "metadata": {
                        k: row[k]
                        for k in (
                            "url",
                            "publisher",
                            "published_at",
                            "title",
                            "feed_id",
                        )
                    },
                    "review": digest,
                    "decision": decisions.get(row["discovery_id"]),
                }
            )
            items.append(
                ReviewItem(
                    "source:" + row["discovery_id"],
                    "source",
                    row["title"],
                    "",
                    status,
                    suggestion,
                    version,
                    "\n".join(details),
                    row["discovery_id"],
                    approvable=not block,
                    block_reason=block,
                    url=row["url"],
                )
            )
        active, stats = active_assessments(
            state_path=self.state_path,
            catalog=self.catalog or real_catalog(),
            model=self.model,
            decisions_path=self.mapping_path,
        )
        mapping_decisions = read_json(self.mapping_path, {"decisions": {}})["decisions"]
        mapping_errors = read_json(
            self.directory / "skill_jobs.json", {"errors": {}}
        ).get("errors", {})
        for entry in active:
            record, news = entry["record"], entry["news"]["packet"]
            digest = fingerprint(record)
            decision = mapping_decisions.get(digest)
            status = (
                "Approved"
                if entry["approved"]
                else "Rejected"
                if decision and decision["decision"] == "reject"
                else "Needs review"
            )
            assessment = record["assessment"]
            details = [
                record["skill"]["label"],
                news["title"],
                news["source"]["source_url"],
                "",
                assessment["rationale"],
                "",
                "APPLIES WHEN",
            ]
            details += ["• " + c for c in assessment["applicability_conditions"]]
            details += ["", "WHAT TO CHECK"] + [
                "• " + c for c in assessment["human_checks"]
            ]
            if record["challenge"]:
                details += ["", "Skeptic: " + record["challenge"]["reason"]]
            details += ["", "SUPPORTING FINDINGS"]
            for finding in news["findings"]:
                if finding["finding_index"] in assessment["finding_indices"]:
                    details += [
                        "• " + finding["claim"],
                        f"  Quote: “{finding['quote']}” — {finding['reference']['passage_id']}",
                    ]
            details += [
                "",
                "Reviewed: " + record["assessed_at"],
                "Models: " + " / ".join(record["returned_models"]),
                "",
                "Approval means conditional skill relevance. Role/task effects and numeric weights require separate review.",
            ]
            block = ""
            if assessment["relevance"] == "not_relevant":
                block = "AI found no supported connection to this skill. There is no positive connection to approve. Read the rationale or ask AI to check again if you disagree."
            elif assessment["relevance"] == "insufficient_evidence":
                block = "The stored findings do not provide enough evidence to approve this skill connection."
            elif news["correction_notices"]:
                block = "Review the source correction notices before approving this connection."
            elif record["status"] != "pending_human_review":
                block = "The evidence check flagged this connection. Read the skeptic's concerns and ask AI to check again before approval."
            elif not entry["news"]["source_approved"]:
                block = "Approve the source first in the Sources view"
            if record["assessment_key"] in mapping_errors:
                block = (
                    "The latest AI check failed; retry before approving this mapping"
                )
                details += [
                    "",
                    "Latest AI check failed. This is the previous assessment.",
                ]
            if status == "Needs review":
                if record["assessment_key"] in mapping_errors:
                    status = "Check failed"
                elif assessment["relevance"] == "not_relevant":
                    status = "No connection found"
                elif assessment["relevance"] == "insufficient_evidence":
                    status = "Insufficient evidence"
                elif (
                    record["status"] != "pending_human_review"
                    or news["correction_notices"]
                ):
                    status = "Check flagged"
                elif not entry["news"]["source_approved"]:
                    status = "Source approval needed"
            details = [
                "STATUS: " + status,
                block or "Ready for your decision.",
                "",
                *details,
            ]
            items.append(
                ReviewItem(
                    "mapping:" + digest,
                    "mapping",
                    news["title"],
                    record["skill"]["label"],
                    status,
                    assessment["relevance"],
                    fingerprint({"record": digest, "decision": decision}),
                    "\n".join(details),
                    record["news_id"],
                    record["skill"]["skill_id"],
                    digest,
                    not block,
                    block,
                    news["source"]["source_url"],
                )
            )
        role_items, role_stats = role_evidence.active_assessments(
            state_path=self.state_path,
            catalog=self.catalog or real_catalog(),
            model=self.model,
            decisions_path=self.role_path,
            skill_decisions_path=self.mapping_path,
        )
        role_decisions = read_json(self.role_path, {"decisions": {}})["decisions"]
        for entry in role_items:
            record, news = entry["record"], entry["news"]["packet"]
            digest = fingerprint(record)
            decision = role_decisions.get(digest)
            assessment = record["assessment"]
            block = entry["block_reason"]
            status = (
                "Approved"
                if entry["approved"]
                else "Rejected"
                if decision and decision["decision"] == "reject"
                else "Check failed"
                if "latest AI role check failed" in block
                else "No connection found"
                if assessment["relevance"] == "not_relevant"
                else "Insufficient evidence"
                if assessment["relevance"] == "insufficient_evidence"
                else "Check flagged"
                if block
                else "Needs review"
            )
            details = [
                "STATUS: " + status,
                block or "Ready for your role impact decision.",
                "",
                record["role"]["role_title"],
                news["title"],
                assessment["rationale"],
                "",
                "ROLE TASKS SUPPORTED BY THESE FINDINGS",
            ]
            details += [
                "• " + t["label"] + " — " + t["task_id"]
                for t in record["role"]["tasks"]
                if t["task_id"] in assessment["task_ids"]
            ]
            details += [
                "",
                "APPLIES WHEN",
                *["• " + c for c in assessment["applicability_conditions"]],
                "",
                "WHAT TO CHECK",
                *["• " + c for c in assessment["human_checks"]],
            ]
            if record["challenge"]:
                details += ["", "Skeptic: " + record["challenge"]["reason"]]
            details += ["", "SUPPORTING FINDINGS"]
            for finding in news["findings"]:
                if finding["finding_index"] in assessment["finding_indices"]:
                    details += [
                        "• " + finding["claim"],
                        f"  Quote: “{finding['quote']}” — {finding['reference']['passage_id']}",
                    ]
            details += [
                "",
                "SHORTLISTED THROUGH SKILLS (not proof of role impact)",
                *[s["skill_id"] for s in record["shortlist"]],
                "",
                "Reviewed: " + record["assessed_at"],
                "Models: " + " / ".join(record["returned_models"]),
                "",
                "Approval means conditional role/task relevance. It does not establish employment effects, task-to-skill links or change learning weights.",
            ]
            if decision:
                details += [
                    "",
                    f"Decision: {decision['decision']} · {decision['reviewer']}",
                    decision.get("reason", ""),
                ]
            items.append(
                ReviewItem(
                    "role:" + digest,
                    "role",
                    news["title"],
                    record["role"]["role_title"],
                    status,
                    assessment["relevance"],
                    fingerprint({"record": digest, "decision": decision}),
                    "\n".join(details),
                    record["news_id"],
                    mapping_sha256=digest,
                    approvable=not block,
                    block_reason=block,
                    url=news["source"]["source_url"],
                    role_id=record["role"]["role_id"],
                )
            )
        return {
            "items": items,
            "stats": stats,
            "role_stats": role_stats,
            "run": self.manifest().get("run"),
            "pending_paths": self.manifest()["pending_paths"],
        }

    def _current(self, key, expected_version):
        item = next((i for i in self.snapshot()["items"] if i.key == key), None)
        if item is None or item.version != expected_version:
            raise ValueError(
                "This item changed. Select its latest review before deciding"
            )
        return item

    def decide(self, key, expected_version, decision, reviewer, note=""):
        if decision not in {"approve", "reject"} or not reviewer.strip():
            raise ValueError("Choose a decision and enter your reviewer name")
        if decision == "reject" and not note.strip():
            raise ValueError("Add a short review note explaining the rejection")
        item = self._current(key, expected_version)
        if decision == "approve" and not item.approvable:
            raise ValueError(item.block_reason)
        if item.kind == "source":
            previous = self._source_decisions().get(item.news_id)
            if decision == "approve":
                queue = read_json(self.state_path, {"items": []})
                row = next(
                    r for r in queue["items"] if r["discovery_id"] == item.news_id
                )
                digest = hashlib.sha256(
                    local_file(self.directory, row["ai_review_path"]).read_bytes()
                ).hexdigest()
                approve_review(
                    item.news_id,
                    reviewer=reviewer,
                    expected_sha256=digest,
                    approve=True,
                    state_path=self.state_path,
                    decisions_path=self.sources_path,
                    registry_path=self.registry_path,
                    expected_previous_decision=previous,
                    reason=note,
                )
            else:
                review_source(
                    item.news_id,
                    decision="reject",
                    reviewer=reviewer,
                    reason=note,
                    state_path=self.state_path,
                    decisions_path=self.sources_path,
                    registry_path=self.registry_path,
                    config_path=self.config_path,
                    expected_previous_decision=previous,
                )
            self._mark_pending(self.sources_path, self.registry_path)
            queue = read_json(self.state_path, {"items": []})
            row = next(r for r in queue["items"] if r["discovery_id"] == item.news_id)
            if row.get("ai_review_path"):
                canonical = self.root / STATE.relative_to(ROOT)
                self._mark_pending(canonical.parent / row["ai_review_path"])
        elif item.kind == "role":
            role_evidence.decide_impact(
                item.mapping_sha256,
                decision=decision,
                reviewer=reviewer,
                reason=note,
                state_path=self.state_path,
                catalog=self.catalog or real_catalog(),
                model=self.model,
                decisions_path=self.role_path,
                skill_decisions_path=self.mapping_path,
            )
            self._mark_pending(self.role_path)
        else:
            if decision == "approve":
                approve_mapping(
                    item.mapping_sha256,
                    reviewer=reviewer,
                    approve=True,
                    state_path=self.state_path,
                    catalog=self.catalog or real_catalog(),
                    model=self.model,
                    decisions_path=self.mapping_path,
                    reason=note,
                )
            else:
                store = read_json(
                    self.mapping_path, {"schema_version": "0.1.0", "decisions": {}}
                )
                previous = store["decisions"].get(item.mapping_sha256)
                entry = {
                    "decision": "reject",
                    "reviewer": reviewer.strip(),
                    "reason": note.strip(),
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "scope": "conditional_skill_relevance_only_no_weights",
                }
                if previous:
                    entry["history"] = [
                        *previous.get("history", []),
                        {k: v for k, v in previous.items() if k != "history"},
                    ]
                store["decisions"][item.mapping_sha256] = entry
                atomic_json(self.mapping_path, store)
            self._mark_pending(self.mapping_path)
        return self.snapshot()

    def recheck(self, key, expected_version, client=None):
        item = self._current(key, expected_version)
        before = {
            p.relative_to(self.directory).as_posix()
            for folder in (
                "ai_reviews",
                "findings",
                "skill_assessments",
                "role_assessments",
            )
            for p in (self.directory / folder).glob("*.json")
        }
        if item.kind == "source":
            result = run_reviews(
                state_path=self.state_path,
                max_reviews=1,
                force=True,
                discovery_ids=[item.news_id],
                client=client,
            )
            failed = result["failed_reviews"]
        elif item.kind == "role":
            result = role_evidence.run_assessments(
                state_path=self.state_path,
                catalog=self.catalog or real_catalog(),
                client=client,
                role_ids=[item.role_id],
                news_ids=[item.news_id],
                force=True,
                max_batches=1,
                skill_decisions_path=self.mapping_path,
            )
            failed = result["failed_batches"]
        else:
            result = run_assessments(
                state_path=self.state_path,
                catalog=self.catalog or real_catalog(),
                client=client,
                skill_ids=[item.skill_id],
                news_ids=[item.news_id],
                force=True,
                max_batches=1,
            )
            failed = result["failed_batches"]
        # Rechecks are persisted even when all model attempts fail, so failures
        # cannot silently become approvals or disappear from the attention list.
        self._mark_pending(self.root / STATE.relative_to(ROOT))
        canonical = self.root / STATE.relative_to(ROOT)
        after = {
            p.relative_to(self.directory).as_posix()
            for folder in (
                "ai_reviews",
                "findings",
                "skill_assessments",
                "role_assessments",
            )
            for p in (self.directory / folder).glob("*.json")
        }
        self._mark_pending(
            *(canonical.parent / reference for reference in after - before)
        )
        return {"snapshot": self.snapshot(), "failed": bool(failed)}

    def trusted_url(self, key, expected_version):
        item = self._current(key, expected_version)
        config = DiscoveryConfig.model_validate_json(self.config_path.read_bytes())
        url = canonical_url(item.url)
        if not any(url.startswith(str(f.article_prefix)) for f in config.feeds):
            raise ValueError("This link is outside the configured research publishers")
        return url

    def publish(self, run_command=None):
        manifest = self.manifest()
        if not manifest["pending_paths"]:
            raise ValueError("There are no local decisions to save to GitHub")
        # Copy only current source references and reviewed/current mapping records,
        # never the credentials, runtime checkpoint files or unrelated repo files.
        self.snapshot()
        canonical = self.root / STATE.relative_to(ROOT)
        references = {"queue.json"}
        for name in manifest["pending_paths"]:
            path = (self.root / name).resolve()
            if path.is_relative_to(canonical.parent.resolve()):
                references.add(path.relative_to(canonical.parent).as_posix())
        queue = read_json(self.state_path, {"items": []})
        for row in queue["items"]:
            if row.get("ai_review_path"):
                references.add(row["ai_review_path"])
                record = read_json(
                    local_file(self.directory, row["ai_review_path"]), {}
                )
                if record.get("candidate_path"):
                    references.add(record["candidate_path"])
        mapping_decisions = read_json(self.mapping_path, {"decisions": {}})["decisions"]
        for path in (self.directory / "skill_assessments").glob("*.json"):
            # Current and rejected mappings are auditable; older unrelated cache
            # history stays in the artifact rather than being bulk-committed.
            if path.stem in mapping_decisions:
                references.add(path.relative_to(self.directory).as_posix())
        role_decisions = read_json(self.role_path, {"decisions": {}})["decisions"]
        for path in (self.directory / "role_assessments").glob("*.json"):
            if path.stem in role_decisions:
                references.add(path.relative_to(self.directory).as_posix())
        for reference in references.copy():
            if reference.startswith("role_assessments/"):
                record = read_json(local_file(self.directory, reference), {})
                references.add(record["source_review_path"])
                references.update(s["assessment_path"] for s in record["shortlist"])
        # Preserve source/candidate provenance for reviewed historical mappings
        # and prior source decisions, even after a later recheck changes the queue.
        for reference in references.copy():
            if reference.startswith("skill_assessments/"):
                record = read_json(local_file(self.directory, reference), {})
                references.add(record["source_review_path"])
        for reference in references.copy():
            if reference.startswith("ai_reviews/"):
                record = read_json(local_file(self.directory, reference), {})
                if record.get("candidate_path"):
                    references.add(record["candidate_path"])
        paths = set(manifest["pending_paths"])
        for reference in references:
            source = local_file(self.directory, reference)
            target = local_file(canonical.parent, reference)
            atomic_bytes(target, source.read_bytes())
            paths.add(target.relative_to(self.root).as_posix())
        allowed = {
            self.sources_path,
            self.registry_path,
            self.mapping_path,
            self.role_path,
        }
        for name in paths:
            path = (self.root / name).resolve()
            if path not in allowed and not path.is_relative_to(
                canonical.parent.resolve()
            ):
                raise ValueError("Publish contains a path outside the review records")

        def git(*args):
            if run_command:
                return run_command(*args)
            result = subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=60,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GCM_INTERACTIVE": "never",
                },
                check=False,
            )
            if result.returncode:
                raise ValueError(
                    "Git could not save the review. Local decisions are kept; ask the assistant to check the branch or GitHub sign-in"
                )
            return result.stdout.strip()

        if (
            git("remote", "get-url", "origin")
            != "https://github.com/ProProcer/here-we-go-sdc.git"
        ):
            raise ValueError(
                "The review menu can publish only to its configured repository"
            )
        if git("branch", "--show-current") != "main":
            raise ValueError("Switch to the main branch before saving review decisions")
        git("add", "--", *sorted(paths))
        changed = git("diff", "--cached", "--name-only", "--", *sorted(paths))
        if changed:
            git(
                "commit",
                "--only",
                "-m",
                "Record human Role 3 review decisions",
                "--",
                *sorted(paths),
            )
        git("push", "origin", "main")
        manifest["pending_paths"] = []
        atomic_json(self.manifest_path, manifest)
        return self.snapshot()
