# Implementation Plan: Add a glossary page to the documentation

## Overview

Add a new glossary page to the Care documentation site with plain-language definitions for frequently used domain terms. The glossary will be accessible via the main navigation bar and available in both versioned docs (3.0 and 3.1).

## Approach

1. **Create glossary content files**
   - Create `versioned_docs/version-3.1/glossary.mdx` with alphabetically sorted domain terms
   - Create `versioned_docs/version-3.0/glossary.mdx` with the same content for version parity
   - Include definitions (1-2 sentences each) for at minimum: facility, encounter, consultation, patient, admission
   - Use plain language appropriate for new contributors

2. **Update navigation sidebar**
   - Modify `sidebars.js` to add a glossary entry to the `tutorialSidebar` array
   - Position the glossary entry logically (e.g., after intro or at the end of the main sections)
   - Use a simple doc reference: `'glossary'`

3. **Verify build integrity**
   - Run `npm run build` to ensure no build errors or broken links
   - Confirm the glossary appears in both version 3.0 and 3.1 documentation
   - Verify search indexing includes the glossary content

## Repos touched

- `agentalec/care_docs` -- documentation site repository, contains versioned docs and sidebar configuration

## New dependencies

None. This change uses existing Docusaurus features and requires no additional packages.

## Implementation notes

- The glossary will be a standalone MDX file, not nested under concepts/flows/references
- All definitions should be sourced from existing concept pages where possible (e.g., encounter from `concepts/clinical/encounter.mdx`)
- The glossary should use standard Markdown formatting for consistency with other docs pages
- Both version 3.0 and 3.1 should receive identical glossary content unless version-specific terms emerge
