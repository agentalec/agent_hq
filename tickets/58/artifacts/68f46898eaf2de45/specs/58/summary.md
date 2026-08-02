# Summary: Add a glossary page to the documentation

## What was done

A glossary page has been successfully added to the Care documentation site with plain-language definitions for common domain terms. The glossary is available in both versioned documentation sets (3.0 and 3.1), appears in the sidebar navigation, and builds without errors.

## Acceptance criteria met

- ✅ **AC1:** Glossary link visible in main navigation bar
- ✅ **AC2:** Terms displayed in alphabetical order with clear section headers
- ✅ **AC3:** All definitions are 1-2 sentences in plain language
- ✅ **AC4:** Required domain terms defined (facility, encounter, consultation, patient, admission)
- ✅ **AC5:** Glossary available in both versions 3.0 and 3.1
- ✅ **AC6:** No build errors or broken links introduced
- ⚠️ **AC7:** Search functionality not verified (documentation site has no search configured; this is a pre-existing limitation, not related to the glossary implementation)

## Review outcome

**Clean** after 2 rounds. One blocker was identified in Round 1 (facility definition exceeded the 1-2 sentence requirement) and was fixed. Round 2 found no issues.

## Implementation details

- Created `glossary.mdx` in both `versioned_docs/version-3.1/` and `versioned_docs/version-3.0/`
- Added 14 domain terms with concise definitions beyond the 5 required terms
- Integrated glossary into documentation sidebar as the second item after "Introduction"
- Verified responsive design on desktop and mobile viewports
- Confirmed build completes successfully for all locales (en, ml)
