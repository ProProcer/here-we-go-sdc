"""Bounded fictional CV intake. PDF decoding runs in a killable child process."""

import json
from pathlib import Path
import subprocess
import sys

from src.schemas.role import Contract

MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
MAX_TEXT = 50_000
MAX_PAGE_STREAM = 2 * 1024 * 1024
PDF_TIMEOUT = 10


class CVParseError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{message} Use the typed-skills form instead.")


class ParsedCV(Contract):
    format: str
    pages: list[str]


def _check_text(pages: list[str]) -> None:
    if sum(len(page) for page in pages) > MAX_TEXT:
        raise CVParseError("text_limit", "Extracted text exceeds 50,000 characters.")
    if not any(page.strip() for page in pages):
        raise CVParseError("no_text", "No readable text found; scanned PDFs need OCR, which is unsupported.")
    if any("\x00" in page for page in pages):
        raise CVParseError("invalid_text", "Input contains unsupported binary text.")


def parse_cv(content: bytes, filename: str) -> ParsedCV:
    """The web adapter must enforce the same upload limit before buffering bytes."""
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if len(content) > MAX_BYTES:
        raise CVParseError("file_limit", "Upload exceeds 2 MiB.")
    if not content:
        raise CVParseError("empty", "The uploaded document is empty.")
    suffix = Path(filename).suffix.casefold()
    if suffix == ".txt":
        try:
            pages = [content.decode("utf-8-sig")]
        except UnicodeDecodeError as error:
            raise CVParseError("encoding", "Plain text must use UTF-8 encoding.") from error
    elif suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise CVParseError("invalid_pdf", "The file does not have a PDF header.")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.profiles.pdf_worker"], input=content,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=PDF_TIMEOUT,
                cwd=Path(__file__).resolve().parents[2], check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise CVParseError("timeout", "PDF processing exceeded its time limit.") from error
        except OSError as error:
            raise CVParseError("worker_unavailable", "PDF processing could not start.") from error
        if result.returncode != 0:
            raise CVParseError("invalid_pdf", "PDF processing failed.")
        try:
            payload = json.loads(result.stdout)
            if "error" in payload:
                raise CVParseError(payload["error"], payload["message"])
            pages = payload["pages"]
            if not isinstance(pages, list) or not all(isinstance(page, str) for page in pages):
                raise ValueError("Invalid worker pages")
        except (ValueError, KeyError, TypeError) as error:
            if isinstance(error, CVParseError):
                raise
            raise CVParseError("invalid_pdf", "PDF returned unreadable output.") from error
    else:
        raise CVParseError("unsupported_format", "Only .txt and text-based .pdf files are supported.")
    _check_text(pages)
    return ParsedCV(format=suffix[1:], pages=pages)
