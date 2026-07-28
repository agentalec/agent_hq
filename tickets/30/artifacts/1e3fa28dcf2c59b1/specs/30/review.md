# Review: Display patient age on encounter page using clinical age-format rules

## Round 1

- **blocker** `tests/PLAYWRIGHT_GUIDE.md:196-213` — unintended formatting change removed all newlines from URL examples, making documentation unreadable; revert lines 196-213 to original formatting.

## Round 2

- **blocker** `src/Utils/utils.ts:246-250` — tooltip is empty string for 0-day-old patients (when years, months, and days are all 0); ensure tooltip always shows at least the display value or "0 days" for newborns.
- **should-fix** `src/Utils/utils.ts:247-249,255,266,278,290,299` — plural forms used for all counts including 1, producing grammatically incorrect text like "1 Days", "1 weeks", "1 months", "1 years"; use singular forms ("day", "month", "year") when count equals 1, or use i18next pluralization with `t(key, {count})`.
- **should-fix** `public/locale/en.json:1719,6636-6637` — inconsistent capitalization produces mixed-case output like "8 weeks 3 Days"; normalize to lowercase ("days": "days") to match "weeks", "months", "years".
