# Fictional CV test files

All people, employers, contact details and qualifications are fictional.

Each domain has PDF, DOCX and TXT versions of the same CV.
Accounting also includes PNG; mechanical engineering includes JPG.

The original in-app sample is [graduate.pdf](../graduate.pdf), available at
http://localhost:8000/api/v2/samples/graduate.pdf while the app runs.

## Files

| Domain | PDF | Word | Text | Image |
| --- | --- | --- | --- | --- |
| Data analytics | [PDF](data_analytics.pdf) | [DOCX](data_analytics.docx) | [TXT](data_analytics.txt) | - |
| Web development | [PDF](web_development.pdf) | [DOCX](web_development.docx) | [TXT](web_development.txt) | - |
| Healthcare / nursing | [PDF](healthcare_nursing.pdf) | [DOCX](healthcare_nursing.docx) | [TXT](healthcare_nursing.txt) | - |
| Finance / accounting | [PDF](finance_accounting.pdf) | [DOCX](finance_accounting.docx) | [TXT](finance_accounting.txt) | [Image](finance_accounting.png) |
| Mechanical engineering | [PDF](mechanical_engineering.pdf) | [DOCX](mechanical_engineering.docx) | [TXT](mechanical_engineering.txt) | [Image](mechanical_engineering.jpg) |

## Actual verification

File parsing and skill consistency: 17/17 passed.
All formats were processed by the app's real document workers, including local OCR for images.
Skill sets were compared with each domain's TXT source; AI is not involved in this comparison.

Live tests uploaded one file per domain, called AI assessment, explicitly confirmed extracted
skills for this automated test, and requested recommendations without target or interest boosts.

| Domain / upload format | AI provider / status | Top recommendation | Domain occupation rank |
| --- | --- | --- | --- |
| Data analytics / .pdf | groq / completed | Economists | 5 |
| Web development / .docx | groq / completed | Web Developers | 1 |
| Healthcare / nursing / .txt | groq / completed | Licensed Practical and Licensed Vocational Nurses | 2 |
| Finance / accounting / .png | groq / completed | Bookkeeping, Accounting, and Auditing Clerks | 3 |
| Mechanical engineering / .jpg | groq / completed | Automotive Engineers | 5 |

## Findings and limits

- HTML and CSS abbreviations now resolve to existing canonical database records, and dotted tool names such as Node.js are preserved during sentence parsing.
- Format consistency compares extracted skills with TXT; it does not establish that every claim was recognized.
- The verifier spaces live calls for the observed Groq token quota. Failed live cases can be retried after cooldown, preserving the original attempt.
- An intended domain occupation in the top five does not guarantee it is the top recommendation; full top-five lists are retained.

Reproduce with `python -m scripts.create_cv_examples` and
`python -m scripts.verify_cv_examples --live` (app running on port 8000).
The verifier spaces live calls to respect the observed Groq quota;
`--retry-failed` repeats only failed live cases after a cooldown.

These tests distinguish successful upload/assessment from recommendation relevance.
The named domain occupation rank is reported even when it is outside the top ten.
A generated CV is test input, not evidence of qualification or licensure.
Full scores, timings, differences and failures are in [test_results.json](test_results.json).
