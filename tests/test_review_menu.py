import copy
import io
import json
import subprocess
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import HTTPHandler, Request, build_opener
from urllib.response import addinfourl

from test_skill_evidence import StubMapper, catalog
from test_source_review import HTML, NOW, ROW, StubReviewer, metadata

from src.intelligence.discovery import CONFIG, DECISIONS, STATE
from src.intelligence.review_github import (
    ArtifactRedirect,
    latest_review_artifact,
    unpack_review_artifact,
)
from src.intelligence.review_menu_service import ROOT, ReviewMenuService
from src.intelligence.skill_evidence import run_assessments
from src.intelligence.source_review import run_reviews
from src.intelligence.sources import DEFAULT_REGISTRY
from src.intelligence.storage import atomic_json


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


class TestReviewDownloads(unittest.TestCase):
    def test_real_redirect_handler_returns_302_without_following_with_auth(self):
        calls = []

        class Transport(HTTPHandler):
            def http_open(self, request):
                calls.append(request)
                response = addinfourl(
                    io.BytesIO(b""),
                    {"Location": "http://artifact.test/signed"},
                    request.full_url,
                    302,
                )
                response.msg = "Found"
                return response

        with self.assertRaises(HTTPError) as caught:
            build_opener(ArtifactRedirect(), Transport()).open(
                Request(
                    "http://github.test/report",
                    headers={"Authorization": "Bearer sentinel"},
                )
            )
        self.assertEqual(caught.exception.code, 302)
        self.assertEqual(len(calls), 1)

    def test_valid_archive_preserves_exact_review_bytes(self):
        raw = archive_bytes(
            {"queue.json": '{"items":[]}\n', "ai_reviews/a.json": '{"test":true}\n'}
        )
        files = unpack_review_artifact(raw)
        self.assertEqual(files["ai_reviews/a.json"], b'{"test":true}\n')

    def test_unsafe_paths_unknown_files_and_invalid_json_are_rejected(self):
        for name in (
            "../secret.json",
            "/secret.json",
            "C:/secret.json",
            "ai_reviews\\..\\secret.json",
            ".env",
            "ai_reviews/deep/a.json",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                unpack_review_artifact(
                    archive_bytes({"queue.json": '{"items":[]}', name: "{}"})
                )
        with self.assertRaises(ValueError):
            unpack_review_artifact(archive_bytes({"queue.json": "not JSON"}))
        with self.assertRaises(ValueError):
            unpack_review_artifact(archive_bytes({"REVIEW_BRIEF.md": "No queue"}))

    def test_github_credential_is_not_forwarded_to_the_artifact_host(self):
        run = {
            "id": 123,
            "html_url": "https://github.com/ProProcer/here-we-go-sdc/actions/runs/123",
            "conclusion": "failure",
            "updated_at": "2026-10-22",
        }
        artifact = {"id": 456, "name": "role3-discovery-state", "expired": False}
        first, second = MagicMock(), MagicMock()
        first.open.side_effect = HTTPError(
            "api-url",
            302,
            "Found",
            {
                "Location": "https://safe.blob.core.windows.net/report?sig=private-download-signature"
            },
            None,
        )
        second.open.return_value.__enter__.return_value.read.return_value = (
            archive_bytes({"queue.json": '{"items":[]}'})
        )
        with (
            patch(
                "src.intelligence.review_github.credential",
                return_value="private-test-credential",
            ),
            patch(
                "src.intelligence.review_github.api",
                side_effect=[{"workflow_runs": [run]}, {"artifacts": [artifact]}],
            ),
            patch(
                "src.intelligence.review_github.build_opener",
                side_effect=[first, second],
            ),
        ):
            files, actual_run = latest_review_artifact()
        self.assertIn("queue.json", files)
        self.assertEqual(actual_run["conclusion"], "failure")
        self.assertEqual(
            first.open.call_args.args[0].get_header("Authorization"),
            "Bearer private-test-credential",
        )
        request = second.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn("private-test-credential", request.full_url)

    def test_signed_download_redirect_to_an_unexpected_host_is_blocked(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError(
            "api-url", 302, "Found", {"Location": "https://example.org/artifact"}, None
        )
        with (
            patch("src.intelligence.review_github.credential", return_value="sentinel"),
            patch(
                "src.intelligence.review_github.api",
                side_effect=[
                    {"workflow_runs": [{"id": 1}]},
                    {
                        "artifacts": [
                            {"id": 2, "name": "role3-discovery-state", "expired": False}
                        ]
                    },
                ],
            ),
            patch("src.intelligence.review_github.build_opener", return_value=opener),
            self.assertRaisesRegex(ValueError, "unexpected artifact"),
        ):
            latest_review_artifact()
        opener.open.assert_called_once()


class TestReviewMenuActions(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.canonical = self.root / STATE.relative_to(ROOT)
        self.config = self.root / CONFIG.relative_to(ROOT)
        self.registry = self.root / DEFAULT_REGISTRY.relative_to(ROOT)
        self.decisions = self.root / DECISIONS.relative_to(ROOT)
        for destination, original in (
            (self.config, CONFIG),
            (self.registry, DEFAULT_REGISTRY),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original.read_bytes())
        atomic_json(self.decisions, {"schema_version": "0.1.0", "decisions": []})
        second = copy.deepcopy(ROW)
        second["discovery_id"] = "b" * 24
        second["url"] = "https://research.google/blog/fictional-second-review-test/"
        atomic_json(self.canonical, {"items": [copy.deepcopy(ROW), second]})
        run_reviews(
            state_path=self.canonical,
            client=StubReviewer(),
            article_fetcher=lambda url: HTML,
            research_fetcher=metadata,
            now=NOW,
        )
        self.catalog = catalog()
        run_assessments(
            state_path=self.canonical,
            catalog=self.catalog,
            client=StubMapper(),
            now=NOW,
        )
        self.service = ReviewMenuService(
            self.root, catalog=self.catalog, model=StubMapper.model
        )
        self.service.snapshot()

    def item(self, kind="source"):
        return next(i for i in self.service.snapshot()["items"] if i.kind == kind)

    def approve_source(self):
        item = self.item()
        with patch("src.intelligence.source_review.fetch_feed", return_value=HTML):
            self.service.decide(item.key, item.version, "approve", "Fictional owner")
        return next(i for i in self.service.snapshot()["items"] if i.key == item.key)

    def test_source_approval_and_conditional_mapping_approval_remain_separate(self):
        mapping = self.item("mapping")
        with self.assertRaisesRegex(ValueError, "Approve the source first"):
            self.service.decide(
                mapping.key, mapping.version, "approve", "Fictional owner"
            )
        source = self.approve_source()
        self.assertEqual(source.status, "Approved")
        mapping = next(
            i
            for i in self.service.snapshot()["items"]
            if i.kind == "mapping" and i.news_id == source.news_id
        )
        self.service.decide(mapping.key, mapping.version, "approve", "Fictional owner")
        mapping = next(
            i for i in self.service.snapshot()["items"] if i.key == mapping.key
        )
        self.assertEqual(mapping.status, "Approved")
        self.assertTrue(self.service.manifest()["pending_paths"])

    def test_reject_and_reapprove_source_keep_audit_history(self):
        source = self.approve_source()
        self.service.decide(
            source.key,
            source.version,
            "reject",
            "Fictional owner",
            "Methods do not fit this use.",
        )
        source = next(
            i for i in self.service.snapshot()["items"] if i.key == source.key
        )
        self.assertEqual(source.status, "Rejected")
        with patch("src.intelligence.source_review.fetch_feed", return_value=HTML):
            self.service.decide(
                source.key,
                source.version,
                "approve",
                "Fictional owner",
                "Reviewed the limitation.",
            )
        decisions = json.loads(self.decisions.read_text())["decisions"]
        self.assertEqual(
            [d["decision"] for d in decisions], ["approve", "reject", "approve"]
        )
        self.assertIn("supersedes_sha256", decisions[-1])

    def test_rejection_needs_reason_and_stale_click_cannot_overwrite_a_decision(self):
        source = self.item()
        with self.assertRaisesRegex(ValueError, "short review note"):
            self.service.decide(source.key, source.version, "reject", "Fictional owner")
        self.approve_source()
        before = self.decisions.read_bytes()
        with self.assertRaisesRegex(ValueError, "item changed"):
            self.service.decide(
                source.key, source.version, "reject", "Fictional owner", "Old view"
            )
        self.assertEqual(before, self.decisions.read_bytes())

    def test_changed_live_article_cannot_be_approved(self):
        item = self.item()
        before = self.registry.read_bytes()
        changed = HTML.replace(
            b"longer tasks had lower success", b"a different result was observed"
        )
        with (
            patch("src.intelligence.source_review.fetch_feed", return_value=changed),
            self.assertRaisesRegex(ValueError, "Article changed"),
        ):
            self.service.decide(item.key, item.version, "approve", "Fictional owner")
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertEqual(json.loads(self.decisions.read_text())["decisions"], [])

    def test_reject_mapping_revokes_conditional_approval_and_preserves_history(self):
        source = self.approve_source()
        mapping = next(
            i
            for i in self.service.snapshot()["items"]
            if i.kind == "mapping" and i.news_id == source.news_id
        )
        self.service.decide(mapping.key, mapping.version, "approve", "Fictional owner")
        mapping = next(
            i for i in self.service.snapshot()["items"] if i.key == mapping.key
        )
        self.service.decide(
            mapping.key,
            mapping.version,
            "reject",
            "Fictional owner",
            "Connection is too broad.",
        )
        mapping = next(
            i for i in self.service.snapshot()["items"] if i.key == mapping.key
        )
        self.assertEqual(mapping.status, "Rejected")
        record = json.loads(self.service.mapping_path.read_text())["decisions"][
            mapping.mapping_sha256
        ]
        self.assertEqual(record["history"][0]["decision"], "approve")

    def test_source_recheck_targets_only_selected_source_including_rejected(self):
        item = self.item()
        self.service.decide(
            item.key, item.version, "reject", "Fictional owner", "Need another check."
        )
        item = next(i for i in self.service.snapshot()["items"] if i.key == item.key)
        client = StubReviewer()
        with (
            patch("src.intelligence.source_review.fetch_feed", return_value=HTML),
            patch(
                "src.intelligence.source_review.fetch_research", side_effect=metadata
            ),
            patch(
                "src.intelligence.review_menu_service.run_reviews", wraps=run_reviews
            ) as run,
        ):
            # Default fetcher arguments are bound at definition time.
            run.side_effect = lambda **kw: run_reviews(
                **kw, article_fetcher=lambda url: HTML, research_fetcher=metadata
            )
            result = self.service.recheck(item.key, item.version, client)
        self.assertFalse(result["failed"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(run.call_args.kwargs["discovery_ids"], [item.news_id])
        self.assertEqual(
            next(i for i in result["snapshot"]["items"] if i.key == item.key).status,
            "Rejected",
        )

    def test_skill_recheck_targets_one_skill_article_pair_and_does_not_approve(self):
        item = self.item("mapping")
        client = StubMapper()
        result = self.service.recheck(item.key, item.version, client)
        self.assertFalse(result["failed"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            [n["news_id"] for n in client.calls[0][1]["news"]], [item.news_id]
        )
        self.assertEqual(client.calls[0][1]["skill"]["skill_id"], item.skill_id)
        self.assertTrue(
            any(
                "skill_assessments/" in p
                for p in self.service.manifest()["pending_paths"]
            )
        )
        self.assertFalse(
            any(i.status == "Approved" for i in result["snapshot"]["items"])
        )

    def test_refresh_does_not_overwrite_unpublished_local_decisions(self):
        self.approve_source()
        download = MagicMock()
        with self.assertRaisesRegex(ValueError, "Save your local decisions"):
            self.service.refresh(download)
        download.assert_not_called()

    def test_publish_only_commits_review_paths_and_keeps_pending_state_if_push_fails(
        self,
    ):
        self.approve_source()
        calls = []

        def git(*args):
            calls.append(args)
            if args[:3] == ("remote", "get-url", "origin"):
                return "https://github.com/ProProcer/here-we-go-sdc.git"
            if args[:2] == ("branch", "--show-current"):
                return "main"
            if args[0] == "push":
                raise ValueError("Fictional push failure")
            return "review changes"

        with self.assertRaisesRegex(ValueError, "push failure"):
            self.service.publish(git)
        self.assertTrue(self.service.manifest()["pending_paths"])
        commit = next(c for c in calls if c[0] == "commit")
        self.assertIn("--only", commit)
        self.assertTrue(all(not p.startswith(".role3-review") for p in commit))
        self.assertTrue(all("GEMINI_API_KEY" not in p for p in commit))
        self.assertTrue(
            all(p.startswith("data/") for p in commit[commit.index("--") + 1 :])
        )

    def test_trusted_source_link_and_local_state_paths_are_scoped(self):
        item = self.item()
        self.assertTrue(
            self.service.trusted_url(item.key, item.version).startswith(
                "https://research.google/blog/"
            )
        )
        with self.assertRaisesRegex(ValueError, "inside this checkout"):
            ReviewMenuService(self.root, state_directory=self.root.parent)

    def test_new_unapproved_recheck_record_is_preserved_when_published(self):
        item = self.item("mapping")
        self.service.recheck(item.key, item.version, StubMapper())
        records = [
            p
            for p in self.service.manifest()["pending_paths"]
            if "/skill_assessments/" in p
        ]
        self.assertEqual(len(records), 1)

        def git(*args):
            if args[:3] == ("remote", "get-url", "origin"):
                return "https://github.com/ProProcer/here-we-go-sdc.git"
            if args[:2] == ("branch", "--show-current"):
                return "main"
            return "review changes" if args[0] == "diff" else ""

        result = self.service.publish(git)
        self.assertEqual(result["pending_paths"], [])
        record_path = self.root / records[0]
        self.assertTrue(record_path.exists())
        record = json.loads(record_path.read_text())
        self.assertTrue((self.canonical.parent / record["source_review_path"]).exists())
        self.assertFalse(any(i.status == "Approved" for i in result["items"]))

    def test_failed_mapping_recheck_preserves_old_review_and_blocks_new_approval(self):
        source = self.approve_source()
        item = next(
            i
            for i in self.service.snapshot()["items"]
            if i.kind == "mapping" and i.news_id == source.news_id
        )
        result = self.service.recheck(item.key, item.version, StubMapper(fail=True))
        self.assertTrue(result["failed"])
        item = next(i for i in result["snapshot"]["items"] if i.key == item.key)
        self.assertFalse(item.approvable)
        self.assertIn("previous assessment", item.details)
        with self.assertRaisesRegex(ValueError, "latest AI check failed"):
            self.service.decide(item.key, item.version, "approve", "Fictional owner")

    def test_publish_retains_the_exact_source_review_approved_before_a_recheck(self):
        item = self.approve_source()
        old_row = next(
            r
            for r in json.loads(self.service.state_path.read_text())["items"]
            if r["discovery_id"] == item.news_id
        )
        old_path = old_row["ai_review_path"]
        old_record = json.loads((self.service.directory / old_path).read_text())
        with patch(
            "src.intelligence.review_menu_service.run_reviews",
            side_effect=lambda **kw: run_reviews(
                **kw, article_fetcher=lambda url: HTML, research_fetcher=metadata
            ),
        ):
            self.service.recheck(item.key, item.version, StubReviewer())

        def git(*args):
            if args[:3] == ("remote", "get-url", "origin"):
                return "https://github.com/ProProcer/here-we-go-sdc.git"
            if args[:2] == ("branch", "--show-current"):
                return "main"
            return "review changes" if args[0] == "diff" else ""

        self.service.publish(git)
        self.assertEqual(
            (self.canonical.parent / old_path).read_bytes(),
            (self.service.directory / old_path).read_bytes(),
        )
        self.assertTrue((self.canonical.parent / old_record["candidate_path"]).exists())

    def test_real_git_publish_leaves_unrelated_staged_work_out_of_the_commit(self):
        def git(*args):
            if args[0] == "push":
                return ""  # Exercise real local Git only; never push test decisions.
            return subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        git("init", "-b", "main")
        git("config", "user.name", "Fictional Test Owner")
        git("config", "user.email", "test@example.org")
        git(
            "remote", "add", "origin", "https://github.com/ProProcer/here-we-go-sdc.git"
        )
        git("add", "data")
        git("commit", "-m", "Test fixture baseline")
        (self.root / "unrelated.txt").write_text("Keep this unrelated work staged.")
        git("add", "unrelated.txt")
        self.approve_source()
        self.service.publish(git)
        self.assertNotIn(
            "unrelated.txt",
            git("show", "--name-only", "--format=", "HEAD").splitlines(),
        )
        self.assertIn(
            "unrelated.txt", git("diff", "--cached", "--name-only").splitlines()
        )
        self.assertEqual(self.service.manifest()["pending_paths"], [])


if __name__ == "__main__":
    unittest.main()
