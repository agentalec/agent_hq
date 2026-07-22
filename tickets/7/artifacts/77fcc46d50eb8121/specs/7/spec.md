# Spec: Add a glossary page to the documentation

## Problem statement

The Care documentation lacks a glossary page where new contributors and readers can quickly look up common domain terms like facility, encounter, consultation, patient, and admission. Contributors currently have to navigate through multiple concept pages or ask maintainers for definitions. A centralized glossary with short, plain-language definitions would improve onboarding and serve as a quick reference for anyone reading the documentation.

## Acceptance criteria

### AC1: Glossary page exists and contains domain terms
**Given** the Care documentation site is built  
**When** I navigate to the glossary page at `/glossary`  
**Then** I see a page titled "Glossary"  
**And** the page contains definitions for at least 20 domain terms including: patient, encounter, consultation, admission, facility, location, organization, user, role, permission, booking, schedule, observation, condition, medication request, supply request, invoice, account, questionnaire, and valueset  
**And** each definition is 1-2 sentences in plain language  
**And** definitions are organized alphabetically

### AC2: Glossary is linked from main navigation
**Given** I am on any page of the Care documentation  
**When** I look at the main navigation sidebar  
**Then** I see a "Glossary" link in the sidebar  
**And** clicking the link navigates to the glossary page

### AC3: Glossary terms link to concept pages where available
**Given** I am viewing the glossary page  
**When** I read a term definition that has a corresponding concept page (e.g., "patient", "encounter", "facility")  
**Then** the term heading is a link to its full concept page  
**And** the link works correctly for the current documentation version

### AC4: Glossary exists in all maintained versions
**Given** the Care documentation supports versions 3.0 and 3.1  
**When** I switch between versions using the version dropdown  
**Then** the glossary page is available and accessible in both versions  
**And** the glossary content reflects terms relevant to each version

## Capability notes

### What already exists
- **Docusaurus configuration**: `docusaurus.config.js` defines the site structure with versioned docs; versions 3.0 and 3.1 are active
- **Sidebar configuration**: `sidebars.js` (line 4) exports `tutorialSidebar` array that controls main documentation navigation
- **Version structure**: `versioned_docs/version-3.0/` and `versioned_docs/version-3.1/` contain versioned documentation
- **Current docs root**: `docs/` contains the latest (unreleased) documentation
- **Concept pages**: Existing concept pages in categories like `concepts/clinical/`, `concepts/facility/`, `concepts/scheduling/` provide detailed definitions that can inform glossary entries
- **Category metadata**: `_category_.json` files (e.g., `versioned_docs/version-3.0/concepts/_category_.json`) define category labels and positions in sidebar

### What needs building
- **Glossary page file**: Create `glossary.mdx` (or `glossary.md`) with term definitions for each version directory and the current docs directory
- **Sidebar integration**: Modify `sidebars.js` to add glossary as a top-level item in `tutorialSidebar` array
- **Term definitions**: Compile 1-2 sentence definitions for 20+ domain terms by distilling existing concept pages
- **Cross-links**: Add markdown links from term headings to their corresponding concept pages using relative paths
- **Alphabetical organization**: Structure the glossary with terms in alphabetical order, potentially using markdown headings or a definition list

## Open questions

1. **Should the glossary be versioned or unversioned?** The ticket doesn't specify. Versioned would mean separate glossary files in `versioned_docs/version-3.0/`, `versioned_docs/version-3.1/`, and `docs/`, with potential term differences across versions. Unversioned would mean a single glossary outside the versioned docs, similar to contributing/ or deployment/ sections. [open: product-owners should decide based on whether domain terms change across Care versions]

2. **What is the preferred sidebar position for the glossary?** Should it appear at the top of the sidebar, at the bottom, or between specific sections like between Flows and References? [open: product-owners can specify in approval or accept implementer's judgment]

3. **Should the glossary include all domain categories or focus on specific ones?** The documentation has 9 concept categories (clinical, facility, scheduling, medications, supply, billing, access-governance, definitions, platform). Should the glossary cover all categories equally or prioritize certain ones? [open: product-owners can refine scope or accept comprehensive coverage of all categories]

4. **What markdown structure should be used for the glossary entries?** Options include H2 headings for each term, an HTML definition list (`<dl>`), or a custom component. [open: implementer can choose based on Docusaurus best practices and markdown conventions used elsewhere in the docs]
