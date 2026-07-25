# Ticket 18: Allow users to customise toast location in Care FE

## Problem Statement

The ticket requests the ability to configure toast notification location via a build-time environment variable and to document this in `example.env`. However, upon investigation, this feature is **already fully implemented** in the codebase. The toast position is already configurable via the `REACT_TOAST_POSITION` environment variable, documented in `.example.env`, and integrated into the application.

## Current Implementation Status

The requested functionality already exists with the following implementation:

1. **Environment variable**: `REACT_TOAST_POSITION` is defined and documented in `.example.env` (lines 106-109)
2. **Configuration**: `care.config.ts` (lines 172-198) parses the environment variable with:
   - Valid positions: `top-left`, `top-center`, `top-right`, `bottom-left`, `bottom-center`, `bottom-right`
   - Default value: `top-center` (not "middle" as mentioned in ticket)
   - Validation logic that warns on invalid values and falls back to default
3. **Integration**: `src/App.tsx` (line 55) passes `careConfig.toastPosition` to the `<Toaster>` component
4. **Component**: `src/components/ui/sonner.tsx` wraps the Sonner library toast component

## Acceptance Criteria

Since the feature is already complete, the following criteria describe what is already implemented and verified:

**AC1: Environment variable configuration**
- **Given** an operator is setting up Care FE
- **When** they set `REACT_TOAST_POSITION` to any valid position value
- **Then** toast notifications should appear at the configured position on the screen

**AC2: Default position**
- **Given** `REACT_TOAST_POSITION` is not set or is empty
- **When** the application loads
- **Then** toast notifications should appear at `top-center` position (the default)

**AC3: Invalid value handling**
- **Given** `REACT_TOAST_POSITION` is set to an invalid value
- **When** the application loads
- **Then** a console warning should be logged listing valid positions
- **And** toast notifications should fall back to `top-center` position

**AC4: Documentation in example.env**
- **Given** a developer is reviewing `.example.env`
- **When** they search for toast configuration
- **Then** they should find `REACT_TOAST_POSITION` documented with:
  - Comment describing it as "Screen position for toast notifications (optional)"
  - List of valid values: `top-left`, `top-center`, `top-right`, `bottom-left`, `bottom-center`, `bottom-right`
  - Note that it defaults to `top-center` if unset or invalid

## Capability Notes

### Already Implemented

- **Environment variable parsing**: `care.config.ts` (lines 176-198) implements the `toastPosition` configuration property
  - Validates against allowed position values
  - Returns default `top-center` for unset or invalid values
  - Logs console warning for invalid values
  
- **Documentation**: `.example.env` (lines 106-109) documents the variable:
  ```env
  # Screen position for toast notifications (optional)
  # Valid values: top-left, top-center, top-right, bottom-left, bottom-center, bottom-right
  # Defaults to top-center if unset or invalid.
  REACT_TOAST_POSITION=
  ```

- **Component integration**: `src/App.tsx` (line 55) applies the configuration:
  ```tsx
  <Toaster
    position={careConfig.toastPosition}
    // ... other props
  />
  ```

- **UI component**: `src/components/ui/sonner.tsx` wraps the Sonner library's `<Toaster>` component, which accepts the `position` prop

### Nothing Needs Building

All requested functionality is already implemented. The ticket may be based on outdated information or a misunderstanding of the current codebase state.

## Open Questions

**[open]** Is there a specific issue with the current implementation that needs addressing? (Product owner to clarify)
- The ticket states the "current default is middle", but the actual default is `top-center`
- All requested functionality (env variable, documentation, configurability) already exists

**[open]** Should this ticket be closed as already complete? (Product owner decision)
- If yes, no implementation work is needed
- If no, what specific behavior change or enhancement is actually desired?

## Recommendation

This ticket should be marked as **already complete** with no implementation work required. The toast position configuration is fully implemented, documented, and functional. If there are specific issues with the current implementation, those should be clarified in a new or updated ticket with concrete examples of the problem.
