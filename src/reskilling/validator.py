"""Bounded, injectable validation of course-page candidates."""

import hashlib
import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from html.parser import HTMLParser
from http.client import HTTPException
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import Field, HttpUrl, model_validator

from src.ingestion.catalog import load_role_catalog
from src.ingestion.selection import Catalog
from src.schemas.roadmap import (
    CourseCost,
    CourseDuration,
    CourseValidationLog,
    ValidationCheck,
    VerifiedCourse,
)
from src.schemas.role import Contract, SkillId

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15


class CourseCandidate(Contract):
    title: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    course_url: HttpUrl
    provider_domains: list[str] = Field(min_length=1)
    source_tier: Literal["trusted", "wider_web"]
    skill_ids: list[SkillId] = Field(min_length=1)
    coverage_strength: dict[SkillId, float]
    cost: CourseCost | None = None
    duration: CourseDuration | None = None
    duration_marker: str | None = None
    prerequisite_skill_ids: list[SkillId] = Field(default_factory=list)
    prerequisite_marker: str | None = None
    delivery_mode: Literal["online", "hybrid", "in_person"]
    language: str | None = None
    country_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate(self):
        if set(self.coverage_strength) != set(self.skill_ids):
            raise ValueError("Candidate coverage must match skill IDs exactly")
        if len(self.skill_ids) != len(set(self.skill_ids)):
            raise ValueError("Candidate skill IDs must be unique")
        if len(self.prerequisite_skill_ids) != len(set(self.prerequisite_skill_ids)):
            raise ValueError("Candidate prerequisite skill IDs must be unique")
        if any(not 0 < value <= 1 for value in self.coverage_strength.values()):
            raise ValueError("Candidate coverage must be finite and within (0, 1]")
        domains = [domain.strip().casefold() for domain in self.provider_domains]
        if any(not domain or "/" in domain or ":" in domain for domain in domains):
            raise ValueError("Provider domains must be bare host names")
        if len(domains) != len(set(domains)):
            raise ValueError("Provider domains must be unique")
        return self


class ValidationOutcome(Contract):
    log: CourseValidationLog
    course: VerifiedCourse | None = None

    @model_validator(mode="after")
    def course_matches_status(self):
        if (self.log.status == "verified") != (self.course is not None):
            raise ValueError("Only verified validation logs may contain a course")
        return self


@dataclass(frozen=True)
class FetchedPage:
    final_url: str
    body: bytes
    fetched_at: datetime


PageFetcher = Callable[[str], FetchedPage]


def _validate_public_https_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Course URLs require HTTPS without credentials or fragments")

    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Course URL host is not public")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(
                    host, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
                )
            }
        except OSError as exc:
            raise ValueError("Course URL host could not be resolved") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Course URL host does not resolve exclusively to public IPs")
    return url


class SafeRedirects(HTTPRedirectHandler):
    """Allow ordinary redirects only after validating every destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        _validate_public_https_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def fetch_course_page(url: str) -> FetchedPage:
    """Fetch one public HTML page with strict time and response-size limits."""

    _validate_public_https_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": "FutureReadyAI/0.1 (course verification)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        },
    )
    started = time.monotonic()
    try:
        with build_opener(SafeRedirects()).open(
            request, timeout=TIMEOUT_SECONDS
        ) as response:
            if response.status != 200:
                raise ValueError("Course page must return HTTP 200")
            if response.headers.get_content_type() not in {
                "text/html",
                "application/xhtml+xml",
            }:
                raise ValueError("Course page must return HTML")
            chunks: list[bytes] = []
            size = 0
            while True:
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise TimeoutError("Course page exceeded the fetch time budget")
                chunk = response.read(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Course page exceeds the response-size limit")
            body = b"".join(chunks)
            if not body:
                raise ValueError("Course page returned an empty response")
            final_url = response.geturl()
            _validate_public_https_url(final_url)
            return FetchedPage(
                final_url=final_url,
                body=body,
                fetched_at=datetime.now(UTC),
            )
    except (HTTPError, URLError, HTTPException, TimeoutError, OSError) as exc:
        raise ValueError("Course page could not be fetched safely") from exc


class CoursePageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.in_title = False
        self.in_heading = False
        self.in_jsonld = False
        self.visible_parts: list[str] = []
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.jsonld_parts: list[str] = []
        self.jsonld_blocks: list[str] = []
        self.language: str | None = None

    def handle_starttag(self, tag, attrs):
        attributes = {key.casefold(): value for key, value in attrs}
        tag = tag.casefold()
        if tag == "html" and attributes.get("lang"):
            self.language = attributes["lang"].split("-")[0]
        if tag == "script" and attributes.get("type", "").casefold() == (
            "application/ld+json"
        ):
            self.in_jsonld = True
            self.jsonld_parts = []
        elif tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.in_heading = True

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "script" and self.in_jsonld:
            self.jsonld_blocks.append("".join(self.jsonld_parts))
            self.in_jsonld = False
            self.jsonld_parts = []
        elif tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        if tag == "title":
            self.in_title = False
        if tag == "h1":
            self.in_heading = False

    def handle_data(self, data):
        if self.in_jsonld:
            self.jsonld_parts.append(data)
            return
        if self.hidden_depth:
            return
        self.visible_parts.append(data)
        if self.in_title:
            self.title_parts.append(data)
        if self.in_heading:
            self.heading_parts.append(data)


@dataclass(frozen=True)
class PageEvidence:
    text: str
    title: str
    language: str | None
    jsonld_objects: tuple[dict, ...]


def _walk_json_objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_json_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json_objects(item)


def extract_page_evidence(body: bytes) -> PageEvidence:
    if not body or len(body) > MAX_BYTES:
        raise ValueError("Course page is empty or oversized")
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Course page is not valid UTF-8") from exc

    parser = CoursePageParser()
    parser.feed(decoded)
    objects: list[dict] = []
    for block in parser.jsonld_blocks:
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        objects.extend(_walk_json_objects(value))

    heading = " ".join(" ".join(parser.heading_parts).split())
    document_title = " ".join(" ".join(parser.title_parts).split())
    return PageEvidence(
        text=" ".join(" ".join(parser.visible_parts).split()),
        title=heading or document_title,
        language=parser.language,
        jsonld_objects=tuple(objects),
    )


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _title_matches(expected: str, observed: str) -> bool:
    expected_norm = _normalized(expected)
    observed_norm = _normalized(observed)
    if not expected_norm or not observed_norm:
        return False
    if expected_norm in observed_norm or observed_norm in expected_norm:
        return True
    return SequenceMatcher(None, expected_norm, observed_norm).ratio() >= 0.72


def _jsonld_course_titles(evidence: PageEvidence) -> list[str]:
    titles = []
    for item in evidence.jsonld_objects:
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if "Course" in types and isinstance(item.get("name"), str):
            titles.append(item["name"])
    return titles


def _host_matches(final_url: str, domains: list[str]) -> bool:
    host = (urlsplit(final_url).hostname or "").rstrip(".").casefold()
    return any(
        host == domain.strip().casefold()
        or host.endswith("." + domain.strip().casefold())
        for domain in domains
    )


def _skill_markers(catalog: Catalog) -> dict[str, list[str]]:
    return {
        skill.skill_id: [skill.label, *skill.aliases]
        for skill in catalog.taxonomy.skills
    }


def _skills_match(
    candidate: CourseCandidate, evidence: PageEvidence, catalog: Catalog
) -> tuple[bool, str]:
    page = _normalized(evidence.text)
    markers = _skill_markers(catalog)
    missing = []
    for skill_id in candidate.skill_ids:
        choices = markers.get(skill_id)
        if not choices:
            missing.append(f"{skill_id} is absent from the shared taxonomy")
        elif not any(
            re.search(r"(?<!\w)" + re.escape(_normalized(choice)) + r"(?!\w)", page)
            for choice in choices
        ):
            missing.append(f"{skill_id} has no documented page marker")
    detail = "; ".join(missing) if missing else "All skills have page evidence"
    return not missing, detail


def _cost_matches(cost: CourseCost, evidence: PageEvidence) -> bool:
    text = evidence.text.casefold()
    offers = [
        item
        for item in evidence.jsonld_objects
        if item.get("@type") == "Offer" or "price" in item or "priceCurrency" in item
    ]
    if cost.access == "free":
        return "free" in text or any(
            str(item.get("price")) in {"0", "0.0"} for item in offers
        )
    if cost.access == "free_to_audit":
        return "free" in text and "audit" in text

    assert cost.currency is not None
    for offer in offers:
        try:
            amount_matches = float(offer.get("price")) == cost.amount
        except (TypeError, ValueError):
            amount_matches = False
        currency_matches = str(offer.get("priceCurrency", "")).upper() == cost.currency
        if amount_matches and currency_matches:
            return True
    amount_markers = {str(cost.amount), f"{cost.amount:.2f}"}
    return cost.currency.casefold() in text and any(
        marker in text for marker in amount_markers
    )


def _availability(evidence: PageEvidence) -> tuple[bool, str]:
    text = evidence.text.casefold()
    negative = (
        "enrollment closed",
        "enrolment closed",
        "course is no longer available",
        "course has been discontinued",
    )
    if any(marker in text for marker in negative):
        return False, "Course page indicates that enrollment is unavailable"
    positive = ("enroll", "enrol", "register", "start learning", "join course")
    if any(marker in text for marker in positive):
        return True, "Course page contains an enrollment or access action"
    return False, "Current enrollment or access could not be confirmed"


def _course_id(candidate: CourseCandidate, final_url: str) -> str:
    slug = "_".join(re.findall(r"[a-z0-9]+", candidate.title.casefold()))[:36]
    digest = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:10]
    return f"course:{slug or 'resource'}_{digest}"


def validate_course_candidate(
    candidate: CourseCandidate,
    *,
    fetcher: PageFetcher = fetch_course_page,
    catalog: Catalog | None = None,
) -> ValidationOutcome:
    """Validate one candidate; uncertainty withholds it instead of guessing."""

    checked_at = datetime.now(UTC)
    try:
        page = fetcher(str(candidate.course_url))
        evidence = extract_page_evidence(page.body)
        checked_at = page.fetched_at
        if checked_at.utcoffset() is None:
            raise ValueError("Fetcher timestamp must include a UTC offset")
    except (ValueError, TimeoutError) as exc:
        log = CourseValidationLog(
            candidate_url=candidate.course_url,
            checked_at=checked_at,
            status="rejected",
            checks=[
                ValidationCheck(
                    name="page_fetch",
                    passed=False,
                    detail=str(exc),
                )
            ],
            reasons=[str(exc)],
        )
        return ValidationOutcome(log=log)

    final_url = page.final_url
    parsed_final = urlsplit(final_url)
    if (
        parsed_final.scheme != "https"
        or not parsed_final.hostname
        or parsed_final.username
        or parsed_final.password
        or parsed_final.fragment
    ):
        return ValidationOutcome(
            log=CourseValidationLog(
                candidate_url=candidate.course_url,
                checked_at=checked_at,
                status="rejected",
                checks=[
                    ValidationCheck(
                        name="final_url",
                        passed=False,
                        detail="Final course URL is not safe HTTPS",
                    )
                ],
                reasons=["Final course URL is not safe HTTPS"],
            )
        )
    page_url = HttpUrl(final_url)
    checks: list[ValidationCheck] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(
            ValidationCheck(
                name=name,
                passed=passed,
                detail=detail,
                evidence_url=page_url,
            )
        )

    provider_ok = _host_matches(final_url, candidate.provider_domains)
    add(
        "provider_domain",
        provider_ok,
        "Provider domain matches"
        if provider_ok
        else "Final URL is outside the declared provider domains",
    )

    titles = [evidence.title, *_jsonld_course_titles(evidence)]
    title_ok = any(_title_matches(candidate.title, title) for title in titles if title)
    add(
        "course_title",
        title_ok,
        "Course title matches page evidence"
        if title_ok
        else "Course title does not match page evidence",
    )

    skill_ok, skill_detail = _skills_match(
        candidate, evidence, catalog if catalog is not None else load_role_catalog()
    )
    add("skill_coverage", skill_ok, skill_detail)

    available, availability_detail = _availability(evidence)
    add("current_availability", available, availability_detail)

    cost_ok = candidate.cost is not None and _cost_matches(candidate.cost, evidence)
    add(
        "cost",
        cost_ok,
        "Cost and currency are evidenced"
        if cost_ok
        else "Cost or currency is unknown or unsupported",
    )

    normalized_page = _normalized(evidence.text)
    duration_ok = bool(
        candidate.duration
        and candidate.duration_marker
        and _normalized(candidate.duration_marker) in normalized_page
    )
    add(
        "duration",
        duration_ok,
        "Duration is evidenced"
        if duration_ok
        else "Duration is unknown or unsupported",
    )

    prerequisites_ok = bool(
        candidate.prerequisite_marker
        and _normalized(candidate.prerequisite_marker) in normalized_page
    )
    add(
        "prerequisites",
        prerequisites_ok,
        "Prerequisites are evidenced"
        if prerequisites_ok
        else "Prerequisites are unknown or unsupported",
    )

    inferred_language = candidate.language or evidence.language
    language_ok = bool(inferred_language)
    add(
        "language",
        language_ok,
        "Course language is identified"
        if language_ok
        else "Course language could not be inferred",
    )

    location_ok = candidate.delivery_mode == "online" or bool(candidate.country_codes)
    add(
        "location",
        location_ok,
        "Delivery availability is identified"
        if location_ok
        else "Non-online course availability is unknown",
    )

    failed = [check for check in checks if not check.passed]
    if failed:
        hard_failures = {"provider_domain", "course_title", "skill_coverage"}
        status = (
            "rejected"
            if any(check.name in hard_failures for check in failed)
            else "withheld"
        )
        reasons = [check.detail for check in failed]
        return ValidationOutcome(
            log=CourseValidationLog(
                candidate_url=candidate.course_url,
                final_url=page_url,
                checked_at=checked_at,
                status=status,
                checks=checks,
                reasons=reasons,
            )
        )

    assert candidate.cost is not None
    assert candidate.duration is not None
    assert inferred_language is not None
    course_id = _course_id(candidate, final_url)
    course = VerifiedCourse(
        course_id=course_id,
        title=candidate.title,
        provider=candidate.provider,
        course_url=page_url,
        evidence_url=page_url,
        source_tier=candidate.source_tier,
        skill_ids=candidate.skill_ids,
        coverage_strength=candidate.coverage_strength,
        cost=candidate.cost,
        duration=candidate.duration,
        prerequisite_skill_ids=candidate.prerequisite_skill_ids,
        delivery_mode=candidate.delivery_mode,
        language=inferred_language,
        country_codes=candidate.country_codes,
        last_verified_at=checked_at,
        validation_notes=["Validated against the current official course page."],
    )
    return ValidationOutcome(
        log=CourseValidationLog(
            candidate_url=candidate.course_url,
            final_url=page_url,
            checked_at=checked_at,
            status="verified",
            checks=checks,
            course_id=course_id,
        ),
        course=course,
    )


def validate_course_candidates(
    candidates: Iterable[CourseCandidate],
    *,
    max_candidates: int = 20,
    fetcher: PageFetcher = fetch_course_page,
    catalog: Catalog | None = None,
) -> list[ValidationOutcome]:
    """Validate no more than the explicit per-run candidate budget."""

    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int):
        raise TypeError("max_candidates must be an integer")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")

    results = []
    for index, candidate in enumerate(candidates):
        if index >= max_candidates:
            break
        results.append(
            validate_course_candidate(
                candidate,
                fetcher=fetcher,
                catalog=catalog,
            )
        )
    return results
