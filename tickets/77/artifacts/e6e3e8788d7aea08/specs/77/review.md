# Review

## Round 1

- **blocker** `tests/PLAYWRIGHT_GUIDE.md:22-39` — Multiple backtick-quoted paths concatenated on single lines; restore original multi-line format with each path on its own line.

## Round 2

- **blocker** Implementation incomplete — The diff only contains formatting fixes to `tests/PLAYWRIGHT_GUIDE.md`; no code changes were made to address the actual issue. The ticket requires making the `geo_organization` field visible and editable in the patient edit flow when navigating from Demographics tab (`section=general-info`). Must implement the organization picker in the edit flow per acceptance criteria 1-6 in spec.
