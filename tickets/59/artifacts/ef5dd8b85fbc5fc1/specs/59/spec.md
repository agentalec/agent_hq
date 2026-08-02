# Spec: Document local development setup for the documentation site

## Problem

The repository README contains local development instructions that reference `yarn`, but the repository uses `npm` (evidenced by `package-lock.json` with no `yarn.lock`). The README also omits the Node.js version requirement (specified in `package.json` as `>=20.0`) and does not tell contributors where to view the rendered site after starting the dev server.

## Acceptance Criteria

1. Given a contributor reads the README, when they check prerequisites, then the README explicitly states Node.js >=20.0 is required.
2. Given a repository with `package-lock.json` and no `yarn.lock`, when the README describes dependency installation, then it uses `npm install` or `npm ci`, not `yarn`.
3. Given a contributor runs the dev server, when they look for the viewing URL, then the README states the site opens at `http://localhost:3000`.
4. Given a contributor reads the local development section, when they follow the commands in order, then each command uses `npm run <script>` instead of `yarn <script>`.
5. Given the package.json defines a `start` script, when the README shows the dev server command, then it references `npm start` or `npm run start`.
6. Given the package.json defines a `build` script, when the README shows the build command, then it references `npm run build`.
7. Given the README mentions deployment commands, when those commands originally used `yarn deploy`, then they are updated to `npm run deploy`.

## Capability Notes

- `README.md` -- exists; contains Installation, Local Development, Build, and Deployment sections currently referencing `yarn`.
- `package.json` -- exists; defines `engines.node: ">=20.0"` and scripts `start`, `build`, `deploy`.
- `package-lock.json` -- exists; confirms npm is the package manager in use.

## Open Questions

None.
