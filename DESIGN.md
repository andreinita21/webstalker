# Design

WebStalker's visual system. Read this before changing any UI: it captures the
tokens, components, and rules that make the surface feel like a single tool.

## Register and goals

- Register: **product**. Design serves the task.
- Reference tools: GitHub, Linear, Vercel, Stripe dashboard. Same calm,
  literal, monospace-friendly tonal register.
- Anti-references: marketing-style SaaS dashboards, gradient hero cards,
  oversized metric tiles, illustrated empty states with mascots.

## Visual principles

1. **State first.** Every screen earns its space by communicating current
   state. Status badge, last-checked time, version count.
2. **Diff is the centerpiece.** When a diff is open, surrounding chrome
   gets quieter so the diff is the loudest thing on the page.
3. **Quiet color, loud meaning.** Neutrals carry the surface. Saturation
   appears only on status badges, diff content, and primary actions.
4. **Density without crampedness.** Tight tables, generous baseline (1.55),
   12.5px monospace, predictable spacing rhythm.
5. **Honest empty and error states.** Empty states explain what is
   missing and offer the next step. Errors print the actual backend
   message in monospace, never a sanitized "Something went wrong".

## Theme

Light by default; the dark variant is a one-line token swap driven by
`prefers-color-scheme`. `color-scheme` is declared in CSS so form
controls and scrollbars also adapt.

## Color tokens

All colors are OKLCH. Neutrals are tinted toward 250° (a cool blue-gray)
at chroma 0.003 to 0.014, never `#000` or `#fff`. Status colors live at
the named hues below.

| Role | Light | Dark |
| --- | --- | --- |
| `--c-bg` | `oklch(0.992 0.003 245)` | `oklch(0.165 0.012 250)` |
| `--c-surface` | `oklch(0.992 0.003 245)` | `oklch(0.190 0.013 250)` |
| `--c-surface-2` | `oklch(0.972 0.005 245)` | `oklch(0.215 0.013 250)` |
| `--c-surface-3` | `oklch(0.948 0.007 245)` | `oklch(0.250 0.013 250)` |
| `--c-border` | `oklch(0.900 0.008 245)` | `oklch(0.290 0.014 250)` |
| `--c-border-strong` | `oklch(0.830 0.010 245)` | `oklch(0.380 0.014 250)` |
| `--c-text` | `oklch(0.220 0.015 250)` | `oklch(0.945 0.005 250)` |
| `--c-text-muted` | `oklch(0.500 0.013 250)` | `oklch(0.700 0.012 250)` |
| `--c-text-subtle` | `oklch(0.650 0.011 250)` | `oklch(0.560 0.013 250)` |
| `--c-accent` (links, focus, primary) | `oklch(0.555 0.130 245)` | `oklch(0.700 0.135 245)` |

### Status hues

Status is encoded as a triplet (foreground, soft background, soft border).
Hue is fixed; the dark theme inverts lightness. Color is never the only
status signal; every status carries text, every diff line carries `+`/`-`/`@`.

| Status | Hue | Used for |
| --- | --- | --- |
| `ok` (green) | 145° | Last scan succeeded with no change. `result=unchanged` log row. |
| `changed` (amber) | 65–85° | Last scan produced a new version. `result=changed` log row. |
| `error` (red) | 25° | Last scan failed. `result=error` log row. Removed diff lines. |
| `pending` (purple) | 290° | Scan currently running, or never run. Pulses subtly. |
| `disabled` / `muted` | neutral | Monitoring off; placeholder pills. |

### Diff palette (GitHub-style, slightly cooler)

| Token | Light | Dark |
| --- | --- | --- |
| `--diff-add-bg` / fg | pale green / dark green | dark green / pale green |
| `--diff-add-num-bg` | saturated pale green | saturated dark green |
| `--diff-del-bg` / fg | pale red / dark red | dark red / pale red |
| `--diff-del-num-bg` | saturated pale red | saturated dark red |
| `--diff-hunk-bg` / fg | pale blue / dark blue | dark blue / pale blue |

Contrast on every diff combination meets WCAG 2.1 AA on body-size text in
both themes.

## Typography

- Body: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI",
  "Inter", system-ui, sans-serif`. System fonts are legitimate here.
- Mono: `ui-monospace, SFMono-Regular, "SF Mono", "JetBrains Mono",
  "Cascadia Mono", Consolas, monospace`. Used for URLs, hashes, paths,
  diffs, log fields, ZIP filenames.

| Step | Size | Used for |
| --- | --- | --- |
| `h1` | 18px / 1.35 | Page title |
| `h2` | 15px / 1.4 | Section title (e.g. empty-state heading) |
| `h3` | 13px / 1.4, uppercase, tracked 0.04em | Sub-headers (rare) |
| body | 14px / 1.55 | Default |
| meta | 12.5px | Sub-titles under page header |
| small | 12px | Help text under labels |
| tiny | 11px | Table thead, badges, kbd |
| diff | 12.5px mono / 1.55 | Diff cells |

Scale ratio is tight (~1.13) to keep many on-screen elements legible
without dramatic jumps in size.

## Spacing scale

Multiples of 4: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`. Page-level rhythm
uses 24/32; component-level uses 4/8/12; diff cells use 0/8 to maximise
content density.

## Radius

Two radii only: `4px` for inline pills/inputs, `6px` for buttons, table
wrappers, fieldsets, and file diffs. No 8px+. No nested radii.

## Component patterns

### Buttons

All buttons share one shape (5px x 11px, 6px radius, 1px border, 13px
weight 500). Variants are color, never silhouette.

| Variant | Use |
| --- | --- |
| `.btn` (default) | Secondary actions |
| `.btn-primary` | Page-level commit (Save, Add website) |
| `.btn-accent` | Reserved; not currently used to keep accent strictly for links/focus |
| `.btn-ghost` | Tertiary, in toolbars and table rows |
| `.btn-danger` | Destructive (Delete) |
| `.btn-sm` | Inside table rows and tight toolbars |

Every button has hover (`+1` surface step), active (`+2` surface step),
focus-visible (3px focus ring at 45% alpha), and disabled (50% opacity)
states.

### Status badges

Pill-shaped, 11.5px, includes a 6px colored dot before the label. The dot
is the same `currentColor`. Pending pulses at 1.4s ease-in-out. The
`.badge-plain` modifier removes the dot for category tags (trigger types
in logs, "primary" file marker).

### Tables

Single canonical pattern wrapped in `.table-wrap` (1px border, 6px
radius). Thead in surface-2 with uppercase 11px letters. Hover row in
surface-2 (no row coloring beyond hover). Numeric columns use tabular
numerals and right-align. The `.row-actions` cell is right-aligned and
collapses ghost buttons. `.hide-sm` columns drop on phones.

### Tabs

Underline tabs, no boxes. Active tab uses the body text color (not the
accent) and a 2px underline of the same color. Counts are pill-shaped
mini-badges (11px) so they don't compete with the label.

### Forms

- All controls share padding (6px x 10px), 6px radius, 1px border-strong.
- Hover deepens the border to text-muted; focus-visible swaps the border
  to accent and adds a 3px focus ring.
- Help text sits under the label or the checkbox label (12px, muted).
- `.form-actions` is a 16px-spaced row with a 1px top border to separate
  it from the form body.

### Empty state

`.empty` is a 1px dashed border on surface, 480px max-width inner column,
left-aligned. Icon (32px, 1px border, 6px radius), then an h2, then a
muted explanation, then exactly one primary action. Compact variant
(`.empty.compact`) reduces padding for in-tab empty states (no versions,
no logs, no diff).

### Flash / banners

Top-of-content banners with `data-autodismiss` so client-side JS fades
them after 5 seconds. `flash-success`, `flash-info`, `flash-error` map to
the status palette.

## Diff viewer rules

The diff is the visual centerpiece. Specifics:

- File diffs are `<details>` wrappers. The first 5 files (and any file
  smaller than 600 lines) render open by default; everything else is
  collapsed to keep huge multi-file diffs scannable.
- File header: monospace path on the left, `+adds / −dels` on the right,
  collapsible chevron rotates from `0deg` to `90deg` on open.
- Per-line layout: `[old# | new# | marker | text]`. Old/new line numbers
  are tabular and right-aligned. The marker column carries `+` / `-` /
  `@` so color is not the only signal.
- Line backgrounds use the soft diff palette (`--diff-add-bg`,
  `--diff-del-bg`); line-number gutters use the saturated variant
  (`--diff-add-num-bg`, `--diff-del-num-bg`). Hunk headers use the soft
  blue band.
- Per-file hard cap: 4000 rendered lines. Anything beyond is truncated
  with an explicit notice and a pointer to the ZIP download.
- Lines wrap (`white-space: pre-wrap; word-break: break-word`) so the
  layout never blows out on long lines, but the gutter is fixed at
  44–60px so content stays aligned.

## Status badge rules

- Always include a text label. Never communicate state by color alone.
- The status order on a website detail page is:
  `Disabled → Scanning → Pending → Changed → Error → OK`. The first
  matching condition wins. This keeps the most actionable state visible.
- A badge with `.badge-pending` carries the 1.4s pulse animation; all
  others are static. `prefers-reduced-motion` disables the pulse.

## Empty / error / loading state rules

- **Empty**: explanatory copy first, then exactly one next-action
  button. No hero illustrations, no mascots.
- **Error**: backend's actual message is shown in monospace 12px in the
  log row's "Detail" column (`.error-text`). No collapsing.
- **Loading**: manual scan buttons swap to "Scanning…" optimistically on
  submit; the real status is reflected on next page load. A pulsing
  `Scanning` badge is shown on the dashboard while the in-process scan
  set contains the website.

## Motion

- 120ms `ease` for color/border transitions on interactive elements.
- 240ms fade for flash dismissal.
- 200ms cubic-bezier(.2, .8, .2, 1) for the toast-style flash slide.
- No animated CSS layout properties. No bounce, elastic, or orchestrated
  page-load sequences.
- All non-essential motion is disabled under `prefers-reduced-motion`.

## Accessibility

- Real `<button>` for actions, `<a>` for navigation, real labels on every
  form control, real `<th>` for table headers.
- Focus ring is always visible on `:focus-visible` and uses a 3px ring at
  45% alpha — strong contrast on every surface in both themes.
- Status conveyed via text, glyph, and color simultaneously.
- WCAG 2.1 AA contrast verified for body-on-bg, muted-on-bg,
  badge-fg-on-badge-bg, diff-fg-on-diff-bg, and link-on-bg in both
  themes.
- `<details>` are used for collapsible diff files so the keyboard can
  toggle them with the standard interaction.
- `<title>` reflects the current page (page title, then product name).

## What is intentionally not here

- A side-stripe accent on cards or rows. Banned globally.
- Gradient text or display fonts in UI labels.
- Glassmorphism. The topbar uses a 60% backdrop-blur but only as a
  legibility aid for the sticky bar, not as decoration.
- A modal layer. Everything is inline or a separate route.
- Toast notifications spawned via JS network calls. Flash messages ride
  on the redirect; the JS only fades them.

## Files of record

- Tokens and components: `webstalker/static/style.css`
- Client behavior: `webstalker/static/app.js` (auto-dismiss, copy buttons,
  optimistic scan-button label)
- Layout shell: `webstalker/templates/base.html`
- Page templates: `webstalker/templates/{dashboard, website_form,
  website_detail, version_detail}.html`
- Diff partial: `webstalker/templates/partials/diff_panel.html`
