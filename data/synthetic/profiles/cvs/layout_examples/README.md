# CV composition and styling tests

These fictional documents vary layout, section ordering and styling rather than just file extension.
ATS-friendly describes the intended plain, single-column structure; no commercial ATS vendor was tested.

Each variant is compared with its source CV in ../domain_examples. All skills must be retained
and no extra skills introduced. The scan uses real local OCR; the other PDFs contain text.

| CV | Composition | Extracted skills | Check |
| --- | --- | --- | --- |
| [analytics_ats_single_column.pdf](analytics_ats_single_column.pdf) | ATS-friendly single column with standard headings; text-based PDF | 9 | passed |
| [analytics_sidebar.pdf](analytics_sidebar.pdf) | Two columns, dark skills sidebar and separate experience column | 9 | passed |
| [analytics_functional.pdf](analytics_functional.pdf) | Functional composition: competencies and project precede work history | 9 | passed |
| [analytics_chronological.docx](analytics_chronological.docx) | Chronological, single-column Word document | 9 | passed |
| [nursing_table_layout.docx](nursing_table_layout.docx) | Two-column Word table with skills and education in a sidebar | 11 | passed |
| [web_two_page.pdf](web_two_page.pdf) | Two-page CV with experience and skills continuing on page two | 10 | passed |
| [accounting_scanned.pdf](accounting_scanned.pdf) | Scanned image-only PDF; no embedded text, requires OCR | 10 | passed |
| [engineering_styled.docx](engineering_styled.docx) | Styled Word CV with colored header and shaded two-column table | 11 | passed |

Run `python -m scripts.create_cv_layout_examples` to regenerate and
`python -m scripts.verify_cv_layout_examples` to repeat the checks.
Full differences and timings: [test_results.json](test_results.json).
