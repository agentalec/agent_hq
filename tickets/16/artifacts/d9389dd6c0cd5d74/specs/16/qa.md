# QA Report: Enhance service points list in queue board

## Summary

⚠️ **Limited Exercise**: Unable to fully exercise the queue board functionality due to lack of backend API. QA performed through code review and analysis of component structure. The implementation appears correct based on code inspection, but user-facing behavior could not be verified in a running application.

## Test Environment

- **Frontend**: React app running on http://localhost:4000 (dev server)
- **Backend**: Not available - queue board requires authentication and active facility/queue data
- **Build**: Production build completed successfully (npm run build)
- **Browser**: Chromium (Playwright installed)

---

## AC1: Desktop service point dropdown placement

**Verdict**: `not-exercised` (code review indicates correct implementation)

### What the code shows:

The implementation correctly moves the `ServicePointsDropDown` component into the "Called + Now Serving" section header:

```typescript
// Lines 208-215 in ManageQueueOngoingTab.tsx
<QueueColumn
  title={t("called_plus_now_serving")}
  options={
    <>
      {/* Desktop: Service points dropdown */}
      <div className="hidden lg:block">
        <ServicePointsDropDown />
      </div>
```

**Evidence from code review**:
- ✅ Dropdown placed inside `QueueColumn` options prop (the serving section header)
- ✅ Uses `className="hidden lg:block"` to show only on desktop (≥1024px)
- ✅ `QueueColumn` component has `bg-gray-100` background for visual distinction (line 450)
- ✅ Reuses existing `ServicePointsDropDown` component without modification

**Why not exercised**: Queue board requires:
1. Valid user authentication
2. Facility ID and Queue ID in URL path (`/facility/:facilityId/practitioner/:practitionerId/queues/:queueId/ongoing`)
3. Backend API to provide service points and token data

![Homepage - Desktop](qa-screenshots/16/homepage-desktop.png)

---

## AC2: Mobile single service point view

**Verdict**: `not-exercised` (code review indicates correct implementation)

### What the code shows:

The implementation adds mobile-specific state and filtering:

```typescript
// Lines 76-77: Mobile state
const [mobileSelectedServicePointId, setMobileSelectedServicePointId] =
  useState<string | null>(null);

// Lines 82-83: Default to first assigned service point
const effectiveMobileServicePointId =
  mobileSelectedServicePointId ?? assignedServicePoints[0]?.id ?? null;

// Lines 86-91: Filter to single service point on mobile
const displayedServicePoints =
  isMobile && effectiveMobileServicePointId
    ? assignedServicePoints.filter(
        (sp) => sp.id === effectiveMobileServicePointId,
      )
    : assignedServicePoints;
```

**Evidence from code review**:
- ✅ Mobile state (`mobileSelectedServicePointId`) separate from desktop multi-select
- ✅ `useBreakpoints({ default: true, lg: false })` correctly identifies mobile (<1024px)
- ✅ `displayedServicePoints` filters to single service point when `isMobile` is true
- ✅ Defaults to first assigned service point via nullish coalescing

**Why not exercised**: Same authentication and backend requirements as AC1.

![Homepage - Mobile](qa-screenshots/16/homepage-mobile.png)

---

## AC3: Mobile service point navigation

**Verdict**: `not-exercised` (code review indicates correct implementation)

### What the code shows:

The `MobileServicePointSelector` component (lines 387-438) implements the dropdown:

```typescript
// Lines 217-223: Mobile selector rendered conditionally
{isMobile && assignedServicePoints.length > 0 && (
  <MobileServicePointSelector
    servicePoints={assignedServicePoints}
    selectedId={effectiveMobileServicePointId}
    onSelect={setMobileSelectedServicePointId}
  />
)}
```

**MobileServicePointSelector component**:
```typescript
// Lines 401-437: Full dropdown implementation
<DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
  <DropdownMenuTrigger asChild>
    <Button variant="outline" size="sm" className="h-8 px-3 gap-2">
      <span className="text-sm font-medium truncate max-w-[150px]">
        {selectedServicePoint?.name || t("select_service_point")}
      </span>
      <ChevronDownIcon className="size-4 shrink-0" />
    </Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent align="end" className="w-64">
    {servicePoints.map((sp) => (
      <button
        key={sp.id}
        onClick={() => {
          onSelect(sp.id);
          setIsOpen(false);
        }}
        className={cn(
          "flex items-center justify-between rounded-sm p-2 text-left hover:bg-gray-100",
          sp.id === selectedId && "bg-gray-100",
        )}
      >
        <span className="text-sm font-medium truncate">{sp.name}</span>
        {sp.id === selectedId && (
          <div className="bg-primary-500 w-2 h-2 rounded-full shrink-0" />
        )}
      </button>
    ))}
  </DropdownMenuContent>
</DropdownMenu>
```

**Evidence from code review**:
- ✅ Lists all available service points in dropdown (maps over `servicePoints`)
- ✅ Visual indicator for selected point: blue dot (`bg-primary-500 w-2 h-2 rounded-full`)
- ✅ Immediate update: `onSelect` callback updates state, triggering re-render
- ✅ No page refresh: React state update only
- ✅ Currently selected point highlighted with `bg-gray-100`

**Why not exercised**: Same authentication and backend requirements as AC1.

---

## AC4: Token card UI consistency

**Verdict**: `not-exercised` (code review indicates correct implementation)

### What the code shows:

The implementation does not modify token card components:

**Evidence from code review**:
- ✅ No changes to `OngoingQueueTokenCard` component (imported on line 35)
- ✅ No changes to `OngoingQueueTokenCardsList` component (used on lines 180-198 and throughout)
- ✅ Filtering happens at service point level (`displayedServicePoints`), not token level
- ✅ Same token rendering logic for both mobile and desktop (lines 237-329)
- ✅ Token actions (mark as serving, complete, etc.) unchanged
- ✅ "Call Next Patient" button preserved in `InServiceColumnOptions` (lines 494-502)

**Why not exercised**: Cannot verify token actions without:
1. Authenticated session with appropriate permissions
2. Active queue with service points assigned
3. Test tokens in various states (waiting, serving, called)

---

## AC5: Desktop multi-service-point display

**Verdict**: `not-exercised` (code review indicates correct implementation)

### What the code shows:

Desktop behavior unchanged except for dropdown placement:

```typescript
// Lines 237-329: Service point mapping logic (unchanged from original)
<div className="flex flex-col gap-4">
  {displayedServicePoints.map((subQueue, index) => (
    <div key={subQueue.id} className="flex flex-col gap-4">
      {index > 0 && (
        <hr className="h-px w-full border border-gray-300 border-dashed" />
      )}
      <div className="flex flex-col p-1 rounded-lg bg-gray-200">
        <div className="flex items-start justify-between gap-2 p-1 pb-2 flex-wrap">
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate">
              {subQueue.name}
            </span>
            <span className="text-xs">
              {t("category")}:{" "}
              {/* ... category display ... */}
```

**Evidence from code review**:
- ✅ On desktop, `displayedServicePoints` equals full `assignedServicePoints` (line 91)
- ✅ Vertical layout with dashed separators between service points (line 241)
- ✅ Each service point shows name, category, "Now Serving", and "Called" tokens
- ✅ `bg-gray-200` background for each service point container (line 243)
- ✅ Existing multi-service-point rendering logic preserved

**Why not exercised**: Same authentication and backend requirements as AC1.

---

## Code Quality Observations

### Positive findings:
- ✅ **Responsive design**: Proper use of Tailwind's `lg:` breakpoint prefix
- ✅ **Type safety**: All new state and props properly typed
- ✅ **Accessibility**: Uses shadcn/ui `DropdownMenu` primitives with ARIA support
- ✅ **State isolation**: Mobile state separate from desktop multi-select
- ✅ **Component extraction**: `MobileServicePointSelector` appropriately abstracted
- ✅ **No breaking changes**: Existing token card components untouched

### Minor notes:
- Mobile service point name has `max-w-[150px]` truncation (line 408) - may be restrictive for long names, but won't break functionality
- Default mobile selection handles empty state correctly via optional chaining

---

## Limits

### What could not be exercised:

1. **No backend API**: The CARE backend (`care` repository) was not available alongside the frontend. Queue board requires:
   - Django backend running on port 9000
   - PostgreSQL database with fixtures loaded
   - Authenticated user session with queue management permissions

2. **Authentication required**: Queue board routes require valid JWT token:
   - Route pattern: `/facility/:facilityId/practitioner/:practitionerId/queues/:queueId/ongoing`
   - No way to navigate to queue board without logging in
   - Test credentials require backend fixture data

3. **Queue-specific data**: Testing acceptance criteria requires:
   - At least one facility with queues configured
   - Multiple service points assigned to a queue
   - Test tokens in various states (waiting, serving, called)
   - Service point categories configured

4. **Responsive behavior**: While code review confirms correct implementation:
   - Could not verify actual mobile vs desktop rendering
   - Could not test service point dropdown interaction
   - Could not verify token card actions work correctly
   - Could not test breakpoint boundaries (1024px transition)

### What was verified:

- ✅ Application builds successfully (production build completed)
- ✅ Development server starts and serves login page
- ✅ Code structure follows established patterns
- ✅ TypeScript compiles without errors
- ✅ Responsive utilities (`useBreakpoints`) imported correctly
- ✅ All UI components (DropdownMenu, Button, etc.) properly imported

### Recommendations:

For complete functional verification, QA requires:

1. **Backend setup**: Follow [CARE backend setup](https://github.com/ohcnetwork/care#self-hosting) to run Django API locally
2. **Database fixtures**: Load test data via `python manage.py load_fixtures`
3. **Test credentials**: Use fixture accounts (e.g., `care-doctor` / `Ohcn@123`)
4. **Queue setup**: Ensure test facility has queues with multiple service points

Once backend is available, re-run QA using Playwright tests with:
```bash
npm run playwright:db-reset          # Create clean DB snapshot
npm run build                         # Build production app
npm run playwright:test               # Run full E2E test suite
```

---

## Conclusion

**Implementation status**: Code review indicates all acceptance criteria are correctly implemented according to the spec.

**User-facing verification**: Not completed due to missing backend API. All acceptance criteria marked as `not-exercised` with code-level evidence provided.

**Blocking issues**: None identified in code review. Implementation follows React/TypeScript best practices and maintains consistency with existing codebase patterns.

**Next step**: Hand off to finalize task with recommendation for human reviewer to perform manual QA with backend once available.
