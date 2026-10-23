"""Downloadable fictional CV, rendered as a real, text-based PDF."""

from io import BytesIO
from pathlib import Path
import textwrap

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "data/synthetic/profiles/cvs/graduate.txt"


def sample_cv_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)

    def font(name):
        return DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject(name)})

    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font("/Helvetica"),
                                              NameObject("/F2"): font("/Helvetica-Bold")})})
    commands = []
    y = 795

    def draw_text(value, *, x=44, size=10, bold=False, gray=0):
        escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        face = "F2" if bold else "F1"
        commands.append(f"{gray} g BT /{face} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({escaped}) Tj ET")

    # This source is an authored fictional fixture; no files in docs are read.
    for index, line in enumerate(SAMPLE_PATH.read_text(encoding="utf-8").splitlines()):
        if index < 4:
            draw_text(line, size=(20, 11, 9, 8)[index], bold=index == 0,
                      gray=0 if index < 2 else 0.35)
            y -= (25, 18, 17, 17)[index]
        elif not line:
            y -= 7
        elif line.isupper():
            draw_text(line, size=10, bold=True)
            commands.append(f"0.7 G 0.5 w 44 {y - 5:.2f} m 551 {y - 5:.2f} l S")
            y -= 21
        elif " | " in line:
            title, year = line.rsplit(" | ", 1)
            draw_text(title, size=10, bold=True)
            draw_text(year, x=551 - len(year) * 9 * 0.556, size=9, gray=0.3)
            y -= 15
        else:
            bullet = line.startswith("- ")
            text = line[2:] if bullet else line
            for number, wrapped in enumerate(textwrap.wrap(text, width=91)):
                if bullet and number == 0:
                    draw_text("-", x=45)
                draw_text(wrapped, x=55 if bullet else 44)
                y -= 13.5
        if y < 40:
            raise ValueError("The fictional sample CV exceeds its one-page layout.")

    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    # Attach the stream as an indirect PDF object so standard viewers can render it.
    page.replace_contents(stream)
    writer.add_metadata({"/Title": "Aisha Tan - Fictional demonstration CV"})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
