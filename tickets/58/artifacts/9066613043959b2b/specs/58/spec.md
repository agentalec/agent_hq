# Spec: Add a glossary page to the documentation

## Problem statement

New contributors struggle to understand domain-specific terms like facility, encounter, and consultation when reading Care documentation. The project currently has no centralized glossary reference, forcing readers to hunt through concept pages or ask maintainers for definitions. A glossary page with concise plain-language definitions for the most frequently used domain terms would reduce onboarding friction and improve documentation discoverability.

## Acceptance criteria

1. Given a user navigates the documentation site, when they view the main navigation bar, then a "Glossary" link is visible.
2. Given a user clicks the "Glossary" link, when the glossary page loads, then all terms are displayed in alphabetical order.
3. Given the glossary page displays terms, when a user reads each definition, then each definition is 1-2 sentences in plain language.
4. Given the glossary includes domain terms, when a user searches for common terms, then facility, encounter, consultation, patient, and admission are all defined.
5. Given the glossary is a versioned document, when a user switches between Care versions (3.0/3.1), then the glossary remains available in both versions.
6. Given the glossary page exists, when the site builds, then no build errors or broken links are introduced.
7. Given a user searches the documentation, when they look for term definitions, then the glossary appears in search results.

## Capability notes

- `sidebars.js` -- exists; exports `tutorialSidebar` array that holds Documentation sidebar structure
- `versioned_docs/version-3.1/intro.mdx` -- exists; serves as the documentation landing page
- `docusaurus.config.js` -- exists; lines 109-125 configure versioned docs plugin with versions 3.1 and 3.0
- `versioned_docs/version-3.1/concepts/clinical/encounter.mdx` -- exists; defines encounter concept (source for glossary entry)
- `versioned_docs/version-3.0/` -- exists; holds version 3.0 docs that must also receive the glossary

## Open questions

None.
