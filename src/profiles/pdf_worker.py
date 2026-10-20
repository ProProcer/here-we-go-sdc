"""Private PDF worker: bounded structured output, no raw CV logging or disk writes."""

from io import BytesIO
import json
import sys

from pypdf import PdfReader

from src.profiles.cv_parser import CVParseError, MAX_BYTES, MAX_PAGES, MAX_PAGE_STREAM, _check_text


def extract_pdf(content: bytes) -> list[str]:
    reader = PdfReader(BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise CVParseError("encrypted", "Encrypted PDFs are unsupported.")
    if len(reader.pages) > MAX_PAGES:
        raise CVParseError("page_limit", "PDF exceeds five pages.")
    pages = []
    for page in reader.pages:
        stream = page.get_contents()
        if stream is not None and len(stream.get_data()) > MAX_PAGE_STREAM:
            raise CVParseError("stream_limit", "PDF page content is too large.")
        pages.append(page.extract_text() or "")
        # Check cumulative length immediately, but allow blank pages within a CV.
        if any(text.strip() for text in pages):
            _check_text(pages)
    _check_text(pages)
    return pages


def main() -> None:
    try:
        content = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise CVParseError("file_limit", "PDF exceeds 2 MiB.")
        payload = {"pages": extract_pdf(content)}
    except CVParseError as error:
        payload = {"error": error.code, "message": "Document cannot be parsed: " + error.code + "."}
    except Exception:
        payload = {"error": "invalid_pdf", "message": "Malformed or unsupported PDF."}
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8"))


if __name__ == "__main__":
    main()
