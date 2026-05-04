# Product

## Register

product

## Users

Developers, sysadmins, technical product owners, and small-business operators
who watch a handful of websites and want to know, precisely and quickly,
when something on those pages has changed. They run WebStalker locally on
their own machine, often alongside terminals, editors, and other developer
tools. The primary task on any screen is to scan a list, judge state, and
drill into the diff that explains a change.

## Product Purpose

WebStalker stores a watchlist of websites in SQLite, scans them on a schedule
(or on demand), saves each materially-different version locally as
content-addressed blobs, and presents the differences as GitHub-style diffs.
Success looks like:

- A user can answer "did anything change since I last looked?" in under
  five seconds on the dashboard.
- When something has changed, the user can read what changed and how,
  inline, with line numbers and added/removed coloring, without
  context switching.
- The version history is portable: any version can be downloaded as a
  self-contained ZIP for inspection or archival.

## Brand Personality

Calm, precise, trustworthy. The same tonal register as a mature developer
tool (GitHub, Linear, Vercel, Stripe dashboard). Confident enough to use
dense data tables and monospace where they help; quiet enough to never get
in the way. No exclamation points. No "magic". The interface explains
exactly what it just did and exactly what will happen next.

## Anti-references

- Marketing-style SaaS dashboards with gradient hero cards and oversized
  metric tiles.
- Childish or playful UIs (rounded illustrations, mascots, soft pastels,
  emoji-as-status).
- Heavy animation, glassmorphism, glowing borders, neon accents.
- Cluttered admin themes that wrap every group in a card with shadow and
  6px+ radius.
- "AI-generated dashboard" reflex aesthetic: navy gradient hero, three
  identical metric cards, pill-shaped CTA, generic blue accent.

## Design Principles

1. **State first, chrome second.** Every screen exists to communicate
   current state: last-checked time, status, version count, diff stats.
   Layout, color, and weight serve that signal and nothing else.
2. **Diff is the centerpiece.** When a diff is open, the rest of the UI
   gets out of the way. Line numbers, monospace, and red/green saturation
   are tuned for fast reading at a glance.
3. **Quiet color, loud meaning.** Color is a status channel, not
   decoration. Most surfaces are tinted neutrals; saturation appears only
   on `changed` / `error` / diff lines.
4. **Honest empty and error states.** Empty states explain what's missing
   and offer the next action. Failed scans surface the actual error
   message in monospace, not a sanitized "Something went wrong."
5. **Local-tool ergonomics.** Optimised for laptop screens running it
   alongside an editor: dense, scannable, keyboard-friendly. Mobile
   doesn't break, but full diff review is a desktop activity.

## Accessibility & Inclusion

- WCAG 2.1 AA target on text contrast against every surface, including
  diff add/remove backgrounds.
- All interactive elements (buttons, tabs, links, table rows used as
  links) have a visible keyboard focus ring.
- Semantic HTML: real `<button>` for actions, `<a>` for navigation, real
  form labels, real table headers.
- Status is never communicated by color alone. Every status badge carries
  a text label; diff lines carry an `+`/`-`/`@` glyph in addition to the
  color.
- `prefers-reduced-motion` honored: no non-essential motion.
