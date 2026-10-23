# Fictional CV test pack

All people, employers and qualifications are invented. Use these files for testing only.

- [Original in-app sample PDF](graduate.pdf)
- [Download all CVs and reports](fictional_cv_examples.zip)
- [Five domains in PDF, DOCX, TXT, PNG and JPG](domain_examples/README.md)
- [Eight compositions and visual layouts](layout_examples/README.md)

The pack includes 17 domain-format variants, eight layout variants and the original
sample PDF. Layouts include a plain ATS-friendly column, colored sidebar, functional
section order, chronological Word document, Word tables, two-page PDF and scanned PDF.
No commercial ATS vendor was tested.

The real parsers preserved catalog skill sets in 17/17 format checks and 8/8 layout
checks. Five live Groq assessments completed with no backup provider on this run.
The report records actual recommendations rather than requiring a particular title
first. These recorded live scores use reviewed_onet_fit_v3. Current matching uses reviewed_onet_fit_v5, which rewards job-relative level suitability and labels software requirement estimates. Re-run the verifier to record current scores.

AI may estimate proficiency only for database-listed CV skills. Unsupported IDs are
excluded; canonical names, skill kinds, definitions and evidence references constrain
assessment. HTML/CSS abbreviations and Node.js are now recognized correctly.

Open the app at http://localhost:8000, upload a CV, review its estimated levels,
confirm the skills that describe it, and find matches. The original sample is also
served at http://localhost:8000/api/v2/samples/graduate.pdf.
