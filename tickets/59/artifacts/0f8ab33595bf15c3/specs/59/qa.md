# QA Report: Document local development setup for the documentation site

## Summary

This ticket involved updating documentation in the README.md file to correctly reflect the repository's tooling (npm instead of yarn) and add missing prerequisite information. As this is a documentation-only change with no user-facing UI, verification was performed by directly examining the README content against each acceptance criterion.

All acceptance criteria have been verified and pass.

---

## Criterion 1: Node.js version requirement

**Verdict:** `pass`

**Verification:** The README now includes a dedicated "Prerequisites" section that explicitly states:

```
## Prerequisites

- Node.js >= 20.0
```

This matches the requirement specified in `package.json` (`"engines": { "node": ">=20.0" }`).

**Note:** As this is documentation content, no application screenshot is applicable. The verification was performed by examining the README.md file directly.

---

## Criterion 2: Use npm install, not yarn

**Verdict:** `pass`

**Verification:** The Installation section now uses `npm install`:

```
## Installation

npm install
```

The repository contains `package-lock.json` (confirmed present) and no `yarn.lock` file (confirmed absent), which supports the use of npm as the package manager.

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Criterion 3: Site viewing URL

**Verdict:** `pass`

**Verification:** The Local Development section now explicitly states where to view the site:

```
This command starts a local development server at `http://localhost:3000` and opens up a browser window.
```

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Criterion 4: Use npm run <script> format

**Verdict:** `pass`

**Verification:** All commands in the Local Development, Build, and Deployment sections use the `npm` format:
- `npm start` (Local Development)
- `npm run build` (Build)
- `npm run deploy` (Deployment)

No `yarn <script>` commands remain in the README.

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Criterion 5: Dev server command uses npm start

**Verdict:** `pass`

**Verification:** The Local Development section shows:

```bash
npm start
```

This correctly references the `start` script defined in `package.json` (`"start": "docusaurus start"`).

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Criterion 6: Build command uses npm run build

**Verdict:** `pass`

**Verification:** The Build section shows:

```bash
npm run build
```

This correctly references the `build` script defined in `package.json` (`"build": "docusaurus build"`).

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Criterion 7: Deployment commands updated from yarn deploy

**Verdict:** `pass`

**Verification:** The Deployment section now uses `npm run deploy`:

```bash
USE_SSH=true npm run deploy
```

and

```bash
GIT_USER=<Your GitHub username> npm run deploy
```

Both deployment commands correctly reference the `deploy` script defined in `package.json` (`"deploy": "docusaurus deploy"`) using npm instead of yarn.

**Note:** As this is documentation content, no application screenshot is applicable.

---

## Limits

This ticket involved documentation-only changes to the README.md file. There is no user-facing application interface to exercise or screenshot. All acceptance criteria were verified by directly examining the README content, package.json configuration, and presence/absence of lock files.

The nature of this ticket means traditional QA with application screenshots is not applicable. Instead, verification consisted of:
1. Confirming README content matches acceptance criteria
2. Cross-referencing with package.json to verify accuracy
3. Confirming repository uses npm (package-lock.json present, yarn.lock absent)

All documentation changes are accurate and complete.
