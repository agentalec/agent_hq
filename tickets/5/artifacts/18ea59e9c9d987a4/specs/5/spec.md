# Spec: Document local development setup for the documentation site

## Problem statement

The documentation repository README.md already contains local development instructions (installation, starting dev server, building, and deployment), but the ticket description states contributors have to guess which package manager and commands to use. Upon investigation, the README.md at the repository root provides clear instructions using `yarn` for installation and `yarn start` for the dev server. The ticket may be based on outdated information or a misunderstanding, as the requested documentation already exists.

## Acceptance criteria

**Given** a contributor has cloned the care_docs repository  
**When** they open README.md in the repository root  
**Then** they see a "Local Development" section with installation instructions, dev server startup commands, and information about where to view the rendered site

**Given** a contributor follows the installation instructions in README.md  
**When** they run the documented package manager installation command  
**Then** dependencies install successfully without errors

**Given** a contributor has installed dependencies  
**When** they run the documented dev server command  
**Then** the development server starts on localhost:3000 and automatically opens a browser

**Given** a contributor reads the README.md prerequisites  
**When** they check the documented Node.js version requirement  
**Then** the requirement matches the `engines.node` field in package.json (>=20.0)

## Capability notes

### Existing capabilities

- **README.md** -- Already contains "Local Development" section (lines 11-17) with `yarn start` command and explanation that it starts a local dev server and opens a browser
- **README.md** -- Already contains "Installation" section (lines 5-9) with `yarn` command
- **README.md** -- Already contains "Build" section (lines 19-25) with `yarn build` command
- **package.json** -- Defines `engines.node: ">=20.0"` requirement (line 46)
- **package.json** -- Defines `start` script as `docusaurus start` (line 7)
- **package-lock.json** -- Present in repository root, indicating npm is the actual package manager used by the tooling (not yarn)

### What needs building

- **Investigation** -- Verify whether the issue is that npm should be used instead of yarn, or if yarn instructions are correct
- **README.md enhancement** -- If needed, add explicit prerequisites section mentioning Node.js >=20.0 requirement
- **README.md enhancement** -- If needed, clarify that localhost:3000 is the default URL for viewing the rendered site
- **README.md enhancement** -- If needed, add beginner-friendly context about what Docusaurus is and why these commands work

## Open questions

- **[open]** Does the repository actually support yarn, or should documentation use npm instead given package-lock.json is present? -- Resolved by testing both package managers locally or checking repository CI configuration.
- **[open]** Is the ticket based on outdated information, or is there a specific gap in the current documentation that wasn't apparent from reading README.md? -- Product owner should clarify the actual gap to address.
- **[open]** Should we add a prerequisites section explicitly listing Node.js >=20.0, or is the existing documentation considered sufficient? -- Product owner decision on documentation completeness level.
