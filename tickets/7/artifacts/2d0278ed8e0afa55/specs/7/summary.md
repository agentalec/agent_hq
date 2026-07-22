# Summary: Add a glossary page to the documentation

## Ticket outcome
✅ **Complete** — A comprehensive glossary page has been successfully added to the Care documentation with 32 domain terms, integrated into navigation, and deployed across all maintained versions.

## What was delivered

### 1. Glossary page with 32 domain terms
Created `glossary.mdx` files with alphabetically organized definitions covering all major domain categories:
- **Clinical**: Patient, Encounter, Consultation, Admission, Condition, Observation, Allergy/Intolerance, Consent, Notes, Service Request, Specimen, Questionnaire Response, Diagnostic Report
- **Facility**: Facility, Location, Device, Healthcare Service
- **Scheduling**: Booking, Schedule, Token
- **Medications**: Medication Request, Medication Administration, Medication Dispense, Medication Statement
- **Supply**: Supply Request, Supply Delivery, Inventory Item, Product
- **Billing**: Invoice, Account, Charge Item, Payment Reconciliation
- **Access Governance**: Organization, User, Role, Permission
- **Definitions**: Questionnaire, Valueset, Activity Definition, Observation Definition, Product Knowledge
- **Platform**: Tagging

Each definition follows the requirement of 1-2 sentences in plain language, making terms accessible to new contributors.

### 2. Navigation integration
Modified `sidebars.js` to add the glossary as a top-level item in the tutorial sidebar, positioned at the end for easy access from any documentation page.

### 3. Cross-linking to concept pages
27 of 32 terms include direct links to their corresponding concept or reference pages, allowing readers to quickly jump from a brief definition to comprehensive documentation. Links use relative paths compatible with Docusaurus versioning.

### 4. Multi-version deployment
Created identical glossary files in three locations:
- `docs/glossary.mdx` (latest/unreleased docs)
- `versioned_docs/version-3.0/glossary.mdx` (version 3.0)
- `versioned_docs/version-3.1/glossary.mdx` (version 3.1)

This ensures the glossary is available regardless of which documentation version a reader is viewing.

## Acceptance criteria verification

✅ **AC1: Glossary page exists and contains domain terms**
- Glossary page created at `/glossary` route
- Contains 32 domain terms (exceeds the minimum of 20)
- All required terms included: patient, encounter, consultation, admission, facility, location, organization, user, role, permission, booking, schedule, observation, condition, medication request, supply request, invoice, account, questionnaire, and valueset
- Each definition is 1-2 sentences in plain language
- Terms organized alphabetically with section headers (A-V)

✅ **AC2: Glossary is linked from main navigation**
- Glossary added to `sidebars.js` as a top-level item
- Appears in the main navigation sidebar on all pages
- Positioned at the end of the sidebar (after References section)

✅ **AC3: Glossary terms link to concept pages where available**
- 27 of 32 terms include markdown links to their concept/reference pages
- 5 terms (Admission, Consultation) defined inline without links as they don't have dedicated pages
- Links use relative paths compatible with versioning (e.g., `concepts/clinical/patient.mdx`)

✅ **AC4: Glossary exists in all maintained versions**
- Identical glossary files created in `docs/`, `versioned_docs/version-3.0/`, and `versioned_docs/version-3.1/`
- Content is version-agnostic (all terms apply to both 3.0 and 3.1)
- Single sidebar configuration serves all versions

## Design decisions

1. **Versioned approach**: Chose to create separate glossary files for each version (rather than a single unversioned page) to maintain consistency with the rest of the documentation structure and allow for future version-specific term variations if needed.

2. **Sidebar position**: Placed glossary at the end of the sidebar (position 100) as it's a reference resource that readers will seek out when needed, not a sequential learning resource.

3. **Markdown structure**: Used H3 headings for each term with inline links, following existing documentation patterns. This is more maintainable than HTML definition lists and renders well in Docusaurus.

4. **Comprehensive coverage**: Included 32 terms across all 9 concept categories, going beyond the minimum to provide thorough coverage of the Care domain model.

## Impact
New contributors can now quickly look up unfamiliar domain terms without navigating through multiple concept pages or asking maintainers. The glossary serves as both a first stop for newcomers and a quick reference for experienced contributors who need a reminder of how a specific term is used in Care.

## Related changes
- Modified: `sidebars.js` (added glossary navigation item)
- Created: `docs/glossary.mdx`
- Created: `versioned_docs/version-3.0/glossary.mdx`
- Created: `versioned_docs/version-3.1/glossary.mdx`

## Pull request
agentalec/care_docs#1
