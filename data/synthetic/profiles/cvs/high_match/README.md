# Fictional high-match CV

[Download PDF](rina_search_marketing.pdf) | [Editable Word CV](rina_search_marketing.docx) | [Plain text](rina_search_marketing.txt)

**Target occupation:** Search Marketing Strategists (`role:onet_13_1161_01`).
**Verified result:** 90.37/100, rank 1, after confirming the explicitly listed proficiency levels.
All names, organizations, qualifications and experiences are fictional. This is a deliberately tailored synthetic benchmark, not a real application CV.

## Important: automatic upload is not the 90.37 result

The live Groq upload assessed only the first 12 of 39 extracted skills, following the current app limit. Confirming the extracted skills without completing the remaining levels scored **31.53/100**.
After setting the skills to the levels printed in this CV and confirming them, the same live profile scored **90.37/100**. No scoring weights or role boosts were changed to produce this result.
The offline check also scored 90.37 without a target-role selection or interests. PDF, DOCX and TXT preserved all 39 intended skills.

## Reproduce in the app

1. Upload the PDF at http://localhost:8000.
2. Review all 39 skills. Set each level to the level printed beside it in the CV, using the optional manual correction control where needed.
3. Confirm the skills and explore careers. Search Marketing Strategists should rank first with 90.37.
4. The CSV below is the complete checklist. The JSON is a programmatic test fixture; the UI does not import it.

[Proficiency checklist (CSV)](proficiency_checklist.csv) | [Reviewed test profile (JSON)](reviewed_profile.json) | [Measured results](test_results.json)

The matching formula remains reviewed_onet_fit_v5. Verification also exposed two parsing issues: canonical Active Learning/Learning Strategies were confused with aspirations, and a generic software substring was counted inside a longer product name. Those were corrected, along with a floating-point boundary issue at complete requirement fulfilment.

## Level checklist

| Skill | Confirmed test level |
| --- | --- |
| Microsoft Excel | intermediate |
| Reading Comprehension | intermediate |
| Active Listening | intermediate |
| Writing | intermediate |
| Speaking | intermediate |
| Mathematics | intermediate |
| Critical Thinking | intermediate |
| Active Learning | intermediate |
| Learning Strategies | intermediate |
| Monitoring | intermediate |
| Social Perceptiveness | intermediate |
| Coordination | intermediate |
| Persuasion | intermediate |
| Negotiation | intermediate |
| Instructing | intermediate |
| Service Orientation | intermediate |
| Complex Problem Solving | intermediate |
| Operations Analysis | intermediate |
| Technology Design | intermediate |
| Programming | intermediate |
| Operations Monitoring | beginner |
| Quality Control Analysis | beginner |
| Judgment and Decision Making | intermediate |
| Systems Analysis | intermediate |
| Systems Evaluation | intermediate |
| Time Management | intermediate |
| Management of Financial Resources | beginner |
| Management of Material Resources | beginner |
| Management of Personnel Resources | intermediate |
| Python | intermediate |
| Hypertext markup language HTML | intermediate |
| Screaming Frog SEO Spider | intermediate |
| Semrush | intermediate |
| Moz search engine optimization SEO software | intermediate |
| Ahrefs Site Explorer | intermediate |
| Adobe Analytics | intermediate |
| Cascading style sheets CSS | intermediate |
| Google | intermediate |
| JavaScript | intermediate |

Regenerate: `python -m scripts.create_high_match_cv`. Verify: `python -m scripts.verify_high_match_cv --live` with the app running.
