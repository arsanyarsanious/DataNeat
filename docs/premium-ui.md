# DataNeat premium interface system

The full visual layer is `frontend/app/premium-theme.css`, imported last in
`frontend/app/layout.tsx`. It owns tokens, typography, surfaces, controls,
modals, the spreadsheet skin and page-specific polish. Workflow components,
markup and the 48px virtual-scroll row geometry were not changed.

## Typography

- Self-hosted **Inter Variable** (`frontend/app/fonts/InterVariable.woff2`,
  SIL Open Font License in `Inter-OFL.txt`). No runtime font request.
- Monospace fallback stack (`JetBrains Mono`, `Cascadia Mono`, `SFMono-Regular`,
  `Consolas`) is used for code-sized data where present.
- Headings use 640–680 weight with tight tracking; body text is regular/medium;
  helper text uses the muted tokens. Spreadsheet numbers use tabular numerals.

## Palette (dark is the default)

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0B0F19` | `#F5F6F8` |
| `--surface` | `#111827` | `#FFFFFF` |
| `--surface-2` / `--panel` | `#1F2937` | `#F3F4F6` / `#FFFFFF` |
| `--text` | `#F9FAFB` | `#0F172A` |
| `--text-body` | `#D1D5DB` | `#374151` |
| `--muted` | `#9CA3AF` | `#6B7280` |
| `--border` | `#374151` | `#E5E7EB` |
| `--green` / `--green-hover` | `#10B981` / `#34D399` | `#059669` / `#10B981` |
| `--shadow` | deep black soft shadow | soft slate shadow |

Existing historical token blocks are re-declared on `.app-shell`,
`.workspace-focused` and the sidebar so scoped overrides do not break the theme.
Dark mode is the default for new visitors; a saved `dataneat-theme` preference
is respected and the light mode was restyled to match the same system. The
sidebar stays dark in both themes.

## Components

- Sidebar: permanent dark surface, mint logo, 3px active indicator, muted menu
  items with gentle hover, compact account/theme section.
- Buttons: dark translucent secondary style; primary mint gradient with dark
  ink (`#052E22`), subtle glow and hover lift; disabled primary falls back to a
  muted surface. All have 180ms transitions.
- Form controls: dark wells, 8px radius, custom chevron, mint focus ring,
  consistent global sizing.
- Cards/panels: `#1F2937` (dark) with 1px borders, 14px radius and deep shadows.
- Spreadsheet: muted uppercase column headers, crisp row borders, tabular
  numerals, soft row hover. Row/cell heights remain exactly 48px.
- Modals: 16px radius, blurred dark backdrop, pill tabs, padded headers.
- Badges/pills: low-contrast neutral capsules; semantic issue tints stay.
- AI actions: indigo→mint gradient border on “Suggest with AI”.
- Cover, login, files, guide, privacy and share pages use the same tokens;
  the cover sample uses mint highlights instead of the old amber tint.
- The correction panel is clamped away from the fixed sidebar on desktop.

## Verification

- Production build, static export and TypeScript passed.
- Headless Chromium reviewed cover, login, upload, Explore, spreadsheet,
  automatic-cleaning modal, column settings, My files, guide, privacy, light
  theme and a 390px mobile viewport with no page errors.
- Live deployment verified: dark class applies without stored preference,
  body background is `rgb(11, 15, 25)`, Inter loads locally, and primary buttons
  compute to the mint gradient with dark text.
- Theme storage keys, collapse persistence, all workflows, audit/history,
  exports and backend behavior are unchanged.
