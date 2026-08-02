# Summary: Document local development setup for the documentation site

## What was done

Updated the README.md to correct package manager references and add missing prerequisite information. The repository uses npm (evidenced by `package-lock.json` with no `yarn.lock`), but the README incorrectly referenced `yarn` throughout. All commands have been updated to use npm, and the Node.js version requirement (>=20.0) has been explicitly documented.

## Acceptance criteria met

All 7 acceptance criteria pass:
- ✅ Added Prerequisites section stating Node.js >=20.0 is required
- ✅ Updated Installation section to use `npm install` instead of yarn
- ✅ Added explicit URL (`http://localhost:3000`) in Local Development section
- ✅ All commands now use `npm run <script>` format throughout README
- ✅ Dev server command uses `npm start`
- ✅ Build command uses `npm run build`
- ✅ Deployment commands updated from `yarn deploy` to `npm run deploy`

## Review outcome

**Clean** — no findings. The implementation passed review on the first round with no issues identified.

## QA outcome

All acceptance criteria verified and pass. Documentation changes are accurate and complete.
