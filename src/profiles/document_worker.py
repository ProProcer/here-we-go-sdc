"""Local document decoding in a killable process; uploads never enter storage."""

import json
import sys
import warnings
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from src.profiles.cv_parser import MAX_BYTES, MAX_PAGES, CVParseError, _check_text
from src.profiles.pdf_worker import extract_pdf

MAX_PIXELS = 8_000_000


def recognize_image(image):
    """CPU OCR, using RapidOCR's packaged models rather than a remote service."""
    import numpy as np
    from rapidocr import RapidOCR

    if image.width * image.height > MAX_PIXELS:
        raise CVParseError("image_limit", "Image exceeds eight megapixels.")
    image = image.convert("RGB")
    engine = RapidOCR(params={"Global.log_level": "error",
                              "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                              "EngineConfig.onnxruntime.inter_op_num_threads": 1})
    result = engine(np.asarray(image))
    return "\n".join(result.txts or [])


def extract_image(content):
    from PIL import Image, ImageOps

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise CVParseError("invalid_image", "Expected a JPEG or PNG image.")
            if image.width * image.height > MAX_PIXELS:
                raise CVParseError("image_limit", "Image exceeds eight megapixels.")
            return [recognize_image(ImageOps.exif_transpose(image))]


def extract_docx(content):
    from docx import Document
    from docx.table import Table

    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 1000 or sum(
                item.file_size for item in archive.infolist()
            ) > 10 * 1024 * 1024:
                raise CVParseError("document_limit", "Expanded DOCX exceeds its limit.")
        document = Document(BytesIO(content))
    except (BadZipFile, KeyError, ValueError) as error:
        raise CVParseError("invalid_docx", "This is not a readable DOCX file.") from error

    def lines(container):
        for block in container.iter_inner_content():
            if isinstance(block, Table):
                for row in block.rows:
                    for cell in row.cells:
                        yield from lines(cell)
            else:
                yield block.text

    text = list(lines(document))
    for section in document.sections:
        text.extend(lines(section.header))
        text.extend(lines(section.footer))
    return ["\n".join(text)]


def extract_pdf_with_ocr(content):
    """Keep PDF validation, and OCR pages that do not have an embedded text layer."""
    from pypdf import PdfReader

    try:
        pages = extract_pdf(content)
    except CVParseError as error:
        if error.code != "no_text":
            raise
        pages = [""] * len(PdfReader(BytesIO(content)).pages)
    if any(not page.strip() for page in pages):
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(content) as document:
            if len(document) > MAX_PAGES:
                raise CVParseError("page_limit", "PDF exceeds five pages.")
            for index, text in enumerate(pages):
                if text.strip():
                    continue
                page = document[index]
                width, height = page.get_size()
                if width * height * 4 > MAX_PIXELS:
                    raise CVParseError("image_limit", "PDF page is too large for OCR.")
                bitmap = page.render(scale=2)
                try:
                    pages[index] = recognize_image(bitmap.to_pil())
                finally:
                    bitmap.close()
                    page.close()
    return pages


def main():
    kind = sys.argv[1]
    try:
        content = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise CVParseError("file_limit", "Upload exceeds 2 MiB.")
        if kind == "pdf":
            pages = extract_pdf_with_ocr(content)
        elif kind == "docx":
            pages = extract_docx(content)
        else:
            pages = extract_image(content)
        _check_text(pages)
        payload = {"pages": pages}
    except CVParseError as error:
        payload = {"error": error.code, "message": "Document cannot be parsed: " + error.code + "."}
    except Exception:
        code = "invalid_pdf" if kind == "pdf" else "invalid_docx" if kind == "docx" else "invalid_image"
        payload = {"error": code, "message": "This document could not be read."}
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8"))


if __name__ == "__main__":
    main()
