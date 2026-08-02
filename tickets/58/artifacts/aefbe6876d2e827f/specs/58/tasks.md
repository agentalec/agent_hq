# Tasks: Add a glossary page to the documentation

## Task 1: Create glossary page and update navigation (care_docs)

**What it touches:**
- `versioned_docs/version-3.1/glossary.mdx` (new file)
- `versioned_docs/version-3.0/glossary.mdx` (new file)
- `sidebars.js` (modification to add glossary navigation entry)

**Dependencies:**
None. This is the only task for this ticket.

**Acceptance criteria covered:**
- AC1: "Glossary" link is visible in main navigation bar
- AC2: All terms are displayed in alphabetical order
- AC3: Each definition is 1-2 sentences in plain language
- AC4: Facility, encounter, consultation, patient, and admission are all defined
- AC5: Glossary remains available in both versions (3.0/3.1)
- AC6: No build errors or broken links are introduced
- AC7: Glossary appears in search results

**Implementation details:**
1. Create `versioned_docs/version-3.1/glossary.mdx` with:
   - Page title: "Glossary"
   - Alphabetically sorted list of domain terms
   - Plain-language definitions (1-2 sentences each) for at minimum:
     - Admission
     - Consultation
     - Encounter
     - Facility
     - Patient
   - Source definitions from existing concept pages where possible
   - Use standard MDX/Markdown formatting

2. Create `versioned_docs/version-3.0/glossary.mdx` with identical content to maintain version parity

3. Modify `sidebars.js`:
   - Add `'glossary'` entry to the `tutorialSidebar` array
   - Position it logically (e.g., after 'intro' or at the end of the sidebar)

4. Verify the implementation:
   - Run `npm run build` to ensure no build errors
   - Confirm glossary appears in both version 3.0 and 3.1
   - Verify navigation link is visible
   - Check that search indexing includes glossary content

**Estimated scope:**
- 2 new files (glossary.mdx × 2 versions)
- 1 modified file (sidebars.js)
- ~50-100 lines of content per glossary file
- Total: ~100-200 changed lines, well under 400-line limit
