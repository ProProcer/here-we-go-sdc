# Fictional high-match CV

[Download PDF](rina_search_marketing.pdf) | [Editable Word CV](rina_search_marketing.docx) | [Plain text](rina_search_marketing.txt)

**Target:** Search Marketing Strategists (`role:onet_13_1161_01`).
**Verified normal upload:** 90.37/100, rank 1. The browser displays 90.4.
Groq assessed all 39 skills. No proficiency overrides or target-role boosts were used.
The original PDF bytes are unchanged. All people, employers and qualifications are fictional.

## Use in the app

1. Refresh http://localhost:8000 and upload the PDF.
2. Review the 39 AI-estimated levels and confirm the skills.
3. Explore careers without changing any level or selecting a target role.
4. Search Marketing Strategists ranks first in the verified run.

[Actual browser screenshot](automatic_upload.png) | [Browser verification](automatic_upload_verification.json) | [API and format results](test_results.json)

## Corrected limitation

The original uploader assessed only the first 12 skills and scored 31.53 after
confirmation. The earlier 90.37 result required a manually completed proficiency
checklist and did not represent normal upload. That prefix limit is now removed.
The complete CV is assessed in one compact request with all skill IDs and evidence
references validated; a partial response cannot be reported as completed.
Profiles over the 100-skill safety cap fail explicitly rather than being truncated.
The matching formula remains reviewed_onet_fit_v5 and was not changed for this fix.

The checklist and reviewed-profile JSON remain transparent synthetic benchmark
references, not inputs to the live browser verification. Live proof uses only the
PDF upload, AI assessment and confirmation, with no imported profile or level edits.

[Reference checklist](proficiency_checklist.csv) | [Reference profile](reviewed_profile.json)

Regenerate: `python -m scripts.create_high_match_cv`.
API/format verification: `python -m scripts.verify_high_match_cv --live`.
Live browser verification: `python -m scripts.verify_rina_upload_browser`.
