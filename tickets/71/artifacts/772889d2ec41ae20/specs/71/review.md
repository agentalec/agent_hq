# Review: Hide SNOMED codes from observations on the patient overview

## Round 1

- **blocker** `src/components/Common/Charts/ObservationHistoryTable.tsx:127` — AC2 violated: when `display` is absent, the fallback should be `code`, not `t("unknown")`. Change to `?.display || observation.main_code?.code || t("unknown")`.
- **blocker** `src/pages/Encounters/tabs/observations.tsx:161` — AC2 violated: when `display` is absent, the fallback should be `code`, not `t("unknown")`. Change to `item.main_code?.display || item.main_code?.code || t("unknown")`.
