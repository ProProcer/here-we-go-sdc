"""Parse bounded HTML into addressable passages without persisting article text."""

import hashlib
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from src.schemas.sources import ApprovedSource

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REPORT_CHARACTERS = 120_000
MIN_REPORT_CHARACTERS = 200
MONTHS = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def find_date_marker(value: date, text: str) -> str | None:
    """Return an explicit date form without inferring abbreviated ranges."""
    forms = (
        value.isoformat(),
        f"{MONTHS[value.month]} {value.day}, {value.year}",
        f"{MONTHS[value.month][:3]} {value.day}, {value.year}",
        f"{value.day} {MONTHS[value.month]} {value.year}",
    )
    normalized = normalize_text(text).casefold()
    return next((form for form in forms if form.casefold() in normalized), None)


def date_is_present(value: date, text: str) -> bool:
    return find_date_marker(value, text) is not None


@dataclass(frozen=True)
class ReportPassage:
    passage_id: str
    section: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParsedReport:
    title: str
    publication_marker: str
    passages: tuple[ReportPassage, ...]
    response_sha256: str
    text_sha256: str
    character_count: int


class ReportHTMLParser(HTMLParser):
    """Keep article/main paragraphs, headings and visible publication metadata."""

    EXCLUDED = frozenset(
        {
            "script",
            "style",
            "noscript",
            "template",
            "nav",
            "footer",
            "aside",
            "svg",
            "form",
            "button",
        }
    )
    VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )
    BLOCKS = frozenset(
        {"p", "li", "blockquote", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.frames: list[tuple[str, bool]] = []
        self.blocks: list[tuple[str, str, bool]] = []
        self.visible: list[str] = []
        self.parts: list[str] = []
        self.kind: str | None = None
        self.in_main = False

    def _flush(self):
        text = normalize_text("".join(self.parts))
        if self.kind and text:
            self.blocks.append((self.kind, text, self.in_main))
        self.parts = []
        self.kind = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        style = (attributes.get("style") or "").replace(" ", "").casefold()
        hidden = (
            bool(self.frames and self.frames[-1][1])
            or tag in self.EXCLUDED
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if tag not in self.VOID:
            self.frames.append((tag, hidden))
        if hidden:
            return
        if tag in self.BLOCKS:
            self._flush()
            self.kind = tag
            self.in_main = any(name in {"main", "article"} for name, _ in self.frames)
        elif tag == "br":
            self.parts.append(" ")
            self.visible.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        hidden = bool(self.frames and self.frames[-1][1])
        if not hidden and tag == self.kind:
            self._flush()
        for index in range(len(self.frames) - 1, -1, -1):
            if self.frames[index][0] == tag:
                del self.frames[index:]
                break
        if not hidden and tag in self.BLOCKS:
            self.visible.append(" ")

    def handle_data(self, data):
        if not self.frames or not self.frames[-1][1]:
            self.visible.append(data)
            if self.kind:
                self.parts.append(data)

    def finish(self):
        self.close()
        self._flush()


def parse_report(body: bytes, source: ApprovedSource) -> ParsedReport:
    if not body or len(body) > MAX_HTML_BYTES:
        raise ValueError("Report HTML is empty or exceeds the size limit")
    parser = ReportHTMLParser()
    parser.feed(body.decode("utf-8"))
    parser.finish()
    titles = [text for kind, text, _ in parser.blocks if kind == "h1"]
    if not titles:
        raise ValueError("Report needs a visible h1 title")
    publication_marker = find_date_marker(source.published_at, " ".join(parser.visible))
    if publication_marker is None:
        raise ValueError(
            "Approved publication date is not present in visible report text"
        )
    use_main = any(main and kind in {"p", "li"} for kind, _, main in parser.blocks)
    headings: dict[int, str] = {1: titles[0]}
    passages = []
    for kind, text, main in parser.blocks:
        if use_main and not main:
            continue
        if kind.startswith("h") and kind[1:].isdigit():
            level = int(kind[1:])
            headings = {
                depth: label for depth, label in headings.items() if depth < level
            }
            headings[level] = text
            continue
        section = " > ".join(headings[key] for key in sorted(headings))
        passages.append(ReportPassage(f"p{len(passages) + 1:04d}", section, text))
    canonical = "\n".join(
        f"{row.passage_id}\t{row.section}\t{row.text}" for row in passages
    )
    characters = len(canonical)
    if not MIN_REPORT_CHARACTERS <= characters <= MAX_REPORT_CHARACTERS:
        raise ValueError(
            "Readable report is too short or exceeds the text limit; no text was truncated"
        )
    return ParsedReport(
        title=titles[0],
        publication_marker=publication_marker,
        passages=tuple(passages),
        response_sha256=hashlib.sha256(body).hexdigest(),
        text_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        character_count=characters,
    )
