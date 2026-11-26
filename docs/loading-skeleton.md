# DataNeat loading skeleton

The app uses a persistent shell skeleton for initial loads, auth resolution,
route transitions and list/detail fetches instead of a blank centered notice.

## Components

`frontend/components/loading-skeleton.tsx`

- `AppSkeleton` — full shell variants:
  - `workspace` — sidebar, top status/actions, heading, stepper and spreadsheet grid.
  - `files` — sidebar, status/actions, file-list cards.
  - `share` — read-only review shell and preview table.
  - `login` — centered sign-in card.
- `LoadingOverlay` — renders the skeleton while loading and keeps it above the
  loaded page for a **200ms opacity fade-out** (`ease-out`).
- `frontend/app/loading.tsx` and segment `loading.tsx` files provide App Router
  transition fallbacks.

## Theme tokens

`frontend/app/skeleton.css` owns the skeleton variables. Dark is the default;
`:root:not(.dark)` supplies light values.

| Token | Dark | Light |
|---|---|---|
| Canvas | `#0B0F19` | `#F8FAFC` |
| Sidebar/card surface | `#111827` | `#FFFFFF` |
| Border | `#1F2937` | `#E2E8F0` |
| Skeleton base | `#1F2937` | `#E2E8F0` |
| Shimmer highlight | `#2D3748` | `#F1F5F9` |
| Active nav tint | `rgba(16,185,129,.12)` | `rgba(16,185,129,.10)` |
| Active nav rail | `#10B981` | `#059669` |
| Status dot | `#10B981` | `#059669` |
| Status text | `#9CA3AF` | `#64748B` |

The active nav item has a 3px left rail and tinted rounded pill. The top status
bar shows a pulsing dot and “Preparing your data environment...” in Inter 13px.
Skeleton blocks use the requested 200% shimmer gradient at 1.5s; reduced-motion
users get static blocks.

## Theme without flash

`frontend/app/layout.tsx` runs a small pre-paint theme script from `<head>` that
adds/removes the `dark` class from `localStorage` before the skeleton paints.
That prevents a dark skeleton flashing on a light preference (or vice versa).

## Where it is used

- `components/account-access.tsx` — auth/config/session resolution.
- `app/workspace/page.tsx` — restoring a saved workspace.
- `app/files/page.tsx` — saved-file list fetch/refresh.
- `app/share/page.tsx` — shared review fetch.
- `app/{workspace,files,share,login}/loading.tsx` and root `app/loading.tsx` —
  route transitions.
- Existing in-sheet and small control progress states remain for local actions.

## Responsive behavior

- Desktop: 246px fixed sidebar; full grid with 6 headers and 11 rows.
- 801–1100px: compact 76px rail.
- ≤800px: horizontal brand/nav bar; grid shows three columns and hides the
  extra columns instead of clipping.
- Status text stays 13px; action placeholders shrink; content padding tightens.

## Verification

- `pnpm exec tsc --noEmit` passed.
- `CLOUDFLARE_EXPORT=1 pnpm run build` passed (10 static pages).
- Playwright captured dark/light at 1440×900 and dark at 390×844; computed
  colors, active rail (`3px`), grid dimensions and shimmer animation matched.
- Fade-out was measured mid-transition (files/share layers below opacity 1,
  removed after the 200ms window); loaded pages rendered with no hydration
  errors.
