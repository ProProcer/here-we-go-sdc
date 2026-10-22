"""Retrieve publisher articles, linked study abstracts, and Crossref metadata.

All destinations are scoped before fetching. Metadata matches are research leads,
not independent corroboration. No generated URL is ever fetched.
"""

import hashlib
import json
import re
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener

from src.intelligence.feeds import RejectRedirects
from src.intelligence.reports import normalize_text, parse_report

MAX_BYTES = 2 * 1024 * 1024


class ArticleLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value)
    return normalize_text(" ".join(parser.parts))


def fetch_research(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.fragment
        or parts.hostname not in {"api.crossref.org", "arxiv.org"}
    ):
        raise ValueError("Unapproved research retrieval destination")
    if parts.hostname == "api.crossref.org" and not parts.path.startswith("/works"):
        raise ValueError("Only Crossref works metadata is supported")
    if parts.hostname == "arxiv.org" and not re.fullmatch(
        r"/abs/\d{4}\.\d{4,5}(v\d+)?", parts.path
    ):
        raise ValueError("Only arXiv abstract pages are supported")
    request = Request(
        url, headers={"User-Agent": "FutureReadyAI/0.3 public-research-review"}
    )
    with build_opener(RejectRedirects()).open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("Research source must return HTTP 200")
        body = response.read(MAX_BYTES + 1)
    if not body or len(body) > MAX_BYTES:
        raise ValueError("Empty or oversized research response")
    return body


def _metadata_document(item, document_id, url, kind, body):
    title = " ".join(item.get("title", []))
    if not title:
        raise ValueError("Study metadata has no title")
    abstract = plain_text(item.get("abstract", ""))
    if len(abstract) > 20_000:
        raise ValueError("Study abstract exceeds review budget")
    authors = [
        " ".join([a.get("given", ""), a.get("family", "")]).strip()
        for a in item.get("author", [])[:8]
    ]
    text = " | ".join(
        [
            title,
            "Publisher: " + item.get("publisher", "unknown"),
            "Authors: " + ", ".join(authors),
            "DOI: " + item.get("DOI", "unknown"),
            "Abstract: " + (abstract or "Not available"),
        ]
    )
    return {
        "document_id": document_id,
        "url": url,
        "title": title,
        "kind": kind,
        "coverage": "publisher_metadata_and_abstract_only"
        if abstract
        else "metadata_only_no_results_checked",
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "notices": item.get("update-to", []),
        "passages": [
            {
                "passage_id": "p0001",
                "section": "Study metadata and abstract",
                "text": text,
            }
        ],
    }


def collect_documents(body, source, *, fetcher=fetch_research):
    report = parse_report(body, source)
    primary = {
        "document_id": "primary",
        "url": str(source.source_url),
        "title": report.title,
        "kind": "publisher_article",
        "coverage": "readable_article_text",
        "response_sha256": report.response_sha256,
        "parsed_text_sha256": report.text_sha256,
        "passages": [
            {"passage_id": p.passage_id, "section": p.section, "text": p.text}
            for p in report.passages
        ],
    }
    documents = [primary]
    attempts = []
    parser = ArticleLinks()
    parser.feed(body.decode("utf-8"))
    study_urls = []
    for href in parser.links:
        url = urljoin(str(source.source_url), href)
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password:
            continue
        if parts.hostname == "arxiv.org":
            match = re.fullmatch(
                r"/(?:abs|pdf|html)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?", parts.path
            )
            if match:
                study_urls.append("https://arxiv.org/abs/" + match[1])
        elif parts.hostname in {"doi.org", "dx.doi.org"} and re.match(
            r"/10\.\d{4,9}/", parts.path
        ):
            study_urls.append(
                "https://api.crossref.org/works/" + quote(parts.path[1:], safe="")
            )
    for url in list(dict.fromkeys(study_urls))[:1]:
        try:
            raw = fetcher(url)
            if len(raw) > MAX_BYTES:
                raise ValueError("Oversized linked study")
            if "api.crossref.org" == urlsplit(url).hostname:
                document = _metadata_document(
                    json.loads(raw)["message"],
                    "linked_study",
                    url,
                    "linked_study_metadata",
                    raw,
                )
            else:
                # arXiv abstract pages contain metadata; never call this full-paper review.
                html = raw.decode("utf-8")
                match = re.search(
                    r'<blockquote[^>]*class="abstract[^"]*"[^>]*>(.*?)</blockquote>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )
                title = re.search(
                    r'<h1[^>]*class="title[^"]*"[^>]*>(.*?)</h1>',
                    html,
                    re.DOTALL | re.IGNORECASE,
                )
                if not match or not title:
                    raise ValueError("Linked abstract was not available")
                document = {
                    "document_id": "linked_study",
                    "url": url,
                    "kind": "linked_study_abstract",
                    "title": plain_text(title[1]),
                    "coverage": "abstract_only_not_full_paper",
                    "response_sha256": hashlib.sha256(raw).hexdigest(),
                    "notices": [],
                    "passages": [
                        {
                            "passage_id": "p0001",
                            "section": "Study abstract",
                            "text": plain_text(match[1]),
                        }
                    ],
                }
            documents.append(document)
            attempts.append(
                {"url": url, "status": "retrieved", "coverage": document["coverage"]}
            )
        except (OSError, ValueError, KeyError, HTTPException) as error:
            attempts.append(
                {"url": url, "status": "unavailable", "error": type(error).__name__}
            )
    # Publisher-supplied bibliographic records provide lateral research leads.
    # They do not establish independence, replication, or absence of retraction.
    query = "https://api.crossref.org/works?" + urlencode(
        {"query.title": report.title, "rows": 3}
    )
    try:
        raw = fetcher(query)
        if len(raw) > MAX_BYTES:
            raise ValueError("Oversized metadata response")
        items = json.loads(raw)["message"]["items"]
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "this",
            "that",
            "into",
            "putting",
            "work",
            "how",
            "our",
            "new",
            "research",
            "ai",
            "agent",
            "agents",
            "model",
            "models",
            "building",
            "blocks",
        }

        def terms(title):
            return {
                word.rstrip("s")
                for word in re.findall(r"[a-z]{3,}", title.casefold())
                if word not in stopwords
            }

        source_terms = terms(report.title)
        retained = 0
        for index, item in enumerate(items[:3]):
            candidate_terms = terms(" ".join(item.get("title", [])))
            if len(source_terms & candidate_terms) < 2:
                continue
            documents.append(
                _metadata_document(
                    item,
                    f"related_{index + 1}",
                    "https://doi.org/" + item["DOI"],
                    "related_study_metadata_candidate",
                    raw,
                )
            )
            retained += 1
        attempts.append(
            {
                "url": query,
                "status": "retrieved",
                "matches": retained,
                "coverage": "metadata_candidates_not_confirmed_corroboration",
            }
        )
    except (OSError, ValueError, KeyError, HTTPException) as error:
        attempts.append(
            {"url": query, "status": "unavailable", "error": type(error).__name__}
        )
    return report, documents, attempts
