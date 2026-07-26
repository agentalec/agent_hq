# Summary: Ticket 17 - Add Recall tab in mobile UI of queue board

## What Was Done

Successfully implemented a mobile-only "Recall" tab in the queue board's Ongoing view, providing mobile users access to tokens with `UNFULFILLED` status (recalled tokens). Previously, recalled tokens were only accessible on desktop via the "Awaiting Recall" dialog link.

## Changes

- **Mobile UI Enhancement**: Added a third tab to the mobile queue board alongside "Waiting" and "Called + Now Serving"
- **Token Display**: Recall tab displays all tokens with `TokenStatus.UNFULFILLED` status using the standard `OngoingQueueTokenCardsList` component
- **Badge Counts**: Real-time count badge on the Recall tab, auto-refreshing every 10 seconds
- **Empty State**: User-friendly message when no recalled tokens exist
- **Desktop Preservation**: Desktop "Awaiting Recall" link and dialog remain unchanged
- **Responsive Design**: Mobile tabs hidden on desktop (≥1024px), Recall tab visible only on mobile

## Acceptance Criteria

All 5 acceptance criteria met:

✅ **AC1**: Three tabs on mobile (Waiting, Called + Now Serving, Recall)  
✅ **AC2**: Recall tab displays `UNFULFILLED` tokens with empty state  
✅ **AC3**: Desktop "Awaiting Recall" link/dialog preserved, no Recall tab on desktop  
✅ **AC4**: Full token actions available (move, call, complete, cancel) via reused card component  
✅ **AC5**: Badge count with auto-refresh displays on Recall tab

## Review Outcome

**Round 1**: 1 blocker (formatting corruption in `tests/PLAYWRIGHT_GUIDE.md`)  
**Round 2**: Blocker resolved, 1 minor nit (removed blank lines in documentation)

**Final Status**: ✅ Approved (0 blockers, 0 should-fix items, 1 nit)

## QA Results

**Status**: Code-verified PASS (limited live testing due to backend dependency requirement)

All acceptance criteria verified through:
- Source code inspection of implementation
- Component structure validation
- Build and dev server verification
- Confirmation that the implementation reuses proven components and follows established patterns

**Note**: Full integration testing with live token data requires a running CARE backend with queue fixtures. Recommended for staging verification before production deployment.

## Implementation Details

**Modified Files**:
- `src/pages/Facility/queues/ManageQueueOngoingTab.tsx` - Added Recall tab and section
- `public/locale/en.json` - Added `no_tokens_awaiting_recall` translation key
- `tests/PLAYWRIGHT_GUIDE.md` - Documentation formatting fix

**Technical Approach**:
- Reused existing `OngoingQueueTokenCardsList` component with `status: TokenStatus.UNFULFILLED` filter
- Followed established mobile tab pattern (consistent with "Waiting" and "Serving" tabs)
- No new abstractions or dependencies introduced
- Proper TypeScript typing and i18n implementation throughout

## Next Steps

Ready for merge to staging. Recommended testing on staging environment with live backend:
1. Create tokens in a queue
2. Recall tokens to generate `UNFULFILLED` status entries
3. Verify Recall tab appears on mobile viewports
4. Confirm token actions work correctly from the Recall tab
5. Verify desktop "Awaiting Recall" link still functions
