# Ticket 63: Allow users to customise toast location in Care FE

## Problem Statement

Toast notifications in Care FE are currently hardcoded to appear at `top-center`. While the codebase already includes infrastructure for customizable toast positioning via `REACT_TOAST_POSITION`, this feature is fully implemented and documented in `.example.env`, making toast location configurable via build-time environment variable.

## Acceptance Criteria

1. Given the `.example.env` file, when reviewing documentation, then `REACT_TOAST_POSITION` is documented with all valid positions (top-left, top-center, top-right, bottom-left, bottom-center, bottom-right) and default value (top-center).
2. Given no `REACT_TOAST_POSITION` is set, when the application loads, then toasts appear at top-center position.
3. Given `REACT_TOAST_POSITION=bottom-right` in environment, when the application loads, then toasts appear at bottom-right position.
4. Given an invalid position value in `REACT_TOAST_POSITION`, when the application loads, then a console warning is shown and toasts fallback to top-center.
5. Given `care.config.ts`, when reviewing the `toastPosition` configuration, then it validates against the six valid Sonner positions.
6. Given `src/App.tsx`, when reviewing the Toaster component, then it uses `careConfig.toastPosition` for the position prop.

## Capability Notes

- `.example.env:106-109` — `REACT_TOAST_POSITION` already documented with valid values and default
- `care.config.ts:176-198` — `toastPosition` configuration with validation exists
- `src/App.tsx:54-63` — `<Toaster position={careConfig.toastPosition} />` already implemented
- `src/components/ui/sonner.tsx:1-30` — Toaster wrapper component exists
- `src/Utils/Notifications.ts:1-56` — Toast notification utilities exist (use `sonner` library)

## Open Questions

None.

---

**Status**: Feature is fully implemented and documented. All acceptance criteria are met in the current codebase.
