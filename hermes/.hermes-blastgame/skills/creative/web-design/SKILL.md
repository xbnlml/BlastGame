---
name: web-design
description: "Web/UI design: design process, brand systems, design tokens, throwaway mockups."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [design, html, ui, ux, prototype, mockup, design-system, tokens, wcag]
---

# Web/UI Design — Unified Guide

Four complementary design modes in one skill. Pick the right mode for the job:

| Mode | Skill Source | Use when the user wants... |
|------|-------------|---------------------------|
| **design** | `claude-design` | A from-scratch designed artifact (landing page, prototype, deck, component lab, motion study) with no specific brand dictated |
| **brand-systems** | `popular-web-designs` | A page styled after a known brand (Stripe, Linear, Vercel, etc.) — 54 real design systems as templates |
| **tokens** | `design-md` | A formal, persistent, machine-readable design-token spec file (DESIGN.md) that lives in a repo |
| **sketch** | `sketch` | Quick 2-3 throwaway HTML mockups to compare visual directions before committing |

**Rule of thumb:** Process + taste, one-off artifact → **design** mode. Match a known brand → **brand-systems**. Author the token spec file → **tokens**. Explore directions before building → **sketch**.

These compose: use `brand-systems` for visual vocabulary, `design` for process, and `sketch` for quick exploration passes.

---

## Mode 1: Design — Full Artifact Design Process

Use when creating a complete designed artifact (landing page, prototype, deck, component lab, motion study).

### Core Identity
Act as an expert designer. HTML is the default tool. Avoid generic web-design tropes unless the user explicitly asks for them.

### Surface-First Composition
Before writing any tokens, name the surface archetype:
1. **Monitor** — watching state change (dashboards, status pages)
2. **Operate** — taking action (consoles, admin panels, inboxes)
3. **Compare** — weighing options (pricing, plans, search results)
4. **Configure** — setting things up (settings, forms, wizards)
5. **Decide/Learn** — being convinced (landing pages, docs) — **only surface where hero + 3 cards is correct**
6. **Explore** — browsing (galleries, maps, catalogs)
7. **Command/Inspect** — keyboard-driven, drill-in (command bars, detail panes)

### Workflow
1. Understand brief → gather context → commit to surface
2. Define design system (colors, type, spacing, radii, shadows)
3. Choose format (static, interactive, deck, component lab)
4. Build → verify → report

### Artifact Rules
- Self-contained HTML with inline `<style>` and `<script>`
- CSS variables for tokens, CSS grid for layout
- semantic HTML, real focus/hover states, `prefers-reduced-motion`
- No filler content, no fake metrics, no decorative stats
- Mobile hit targets >= 44px

### Slop Self-Audit (Score before fixing)
10 tells: tech gradient, generic indigo hue, feature-tile grid, accent rail, unearned blur, monument stat, icon topper, center stack, default type, wrong surface. Score out of 10; diagnose before treating.

### Content Discipline
Every element must earn its place. No fake metrics, decorative stats, generic feature grids, unnecessary icons, placeholder testimonials.

### Motion
Clarifies state changes, reduces anxiety, shows continuity. Not theater.

---

## Mode 2: Brand Systems — 54 Real Design Templates

Load any brand's design system from `templates/`:

```
skill_view(name="web-design", file_path="templates/<brand>.md")
```

Each template includes: CDN font link, color palette as CSS custom properties, typography hierarchy, component styles (buttons, cards, nav, inputs), spacing system, shadows, responsive patterns.

### Supported Brands (54)

**AI/ML:** Claude, Cohere, ElevenLabs, Minimax, Mistral, Ollama, OpenCode, Replicate, RunwayML, Together AI, VoltAgent, xAI

**Developer Tools:** Cursor, Expo, Linear, Lovable, Mintlify, PostHog, Raycast, Resend, Sentry, Supabase, Superhuman, Vercel, Warp, Zapier

**Infrastructure:** ClickHouse, Composio, HashiCorp, MongoDB, Sanity, Stripe

**Design/Productivity:** Airtable, Cal.com, Clay, Figma, Framer, Intercom, Miro, Notion, Pinterest, Webflow

**Fintech:** Coinbase, Kraken, Revolut, Wise

**Enterprise/Consumer:** Airbnb, Apple, BMW, IBM, NVIDIA, SpaceX, Spotify, Uber

### Choosing a Brand
- Developer tools: Linear, Vercel, Supabase, Sentry
- Docs/content: Mintlify, Notion, Sanity, MongoDB
- Marketing: Stripe, Framer, Apple, SpaceX
- Dark mode: Linear, Cursor, ElevenLabs, Warp
- Light/clean: Vercel, Stripe, Notion, Replicate
- Premium: Apple, BMW, Stripe, Superhuman

### Font Substitution
Proprietary fonts map to Google Fonts: Geist→Geist, sohne-var→Source Sans 3, Circular→DM Sans, Berkeley Mono→JetBrains Mono, etc.

### HTML Generation Pattern
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Paste template's CDN font <link> -->
  <link href="..." rel="stylesheet">
  <style>
    :root { --color-bg: ...; --color-text: ...; --color-accent: ...; }
    body { font-family: 'Inter', system-ui, sans-serif; }
  </style>
</head>
<body>
  <!-- Build using template's component specs -->
</body>
</html>
```

---

## Mode 3: Design Tokens — DESIGN.md Spec Files

DESIGN.md is Google's open spec for describing a visual identity to coding agents. One file = YAML frontmatter (machine tokens) + Markdown body (human rationale).

### File Anatomy
```markdown
---
version: alpha
name: Heritage
colors:
  primary: "#1A1C1E"
  secondary: "#6C7278"
  tertiary: "#B8422E"
  neutral: "#F7F5F2"
typography:
  h1:
    fontFamily: Public Sans
    fontSize: 3rem
    fontWeight: 700
spacing:
  sm: 8px
  md: 16px
  lg: 24px
---
## Overview
Architectural minimalism meets journalistic gravitas...
```

### Token Types
- **Color**: `#` + hex (sRGB), quoted strings: `"#1A1C1E"`
- **Dimension**: number + unit: `48px`, `"-0.02em"`
- **Token reference**: `{colors.primary}`
- **Typography**: object with `fontFamily, fontSize, fontWeight, lineHeight, letterSpacing`

### Workflow
1. Write `DESIGN.md` in project root
2. Lint: `npx -y @google/design.md lint DESIGN.md`
3. Diff: `npx -y @google/design.md diff DESIGN.md DESIGN-v2.md`
4. Export: `npx -y @google/design.md export --format tailwind DESING.md > tailwind.theme.json`

### Canonical Sections (in order)
1. Overview (alias: Brand & Style)
2. Colors
3. Typography
4. Layout (alias: Layout & Spacing)
5. Elevation & Depth
6. Shapes
7. Components
8. Do's and Don'ts

### Lint Rules
- `broken-ref` (error) — `{colors.missing}` points nowhere
- `duplicate-section` (error) — same heading twice
- `wcag-contrast` (warning) — component textColor vs backgroundColor ratio vs WCAG AA/AAA
- Component variants are **separate entries** (`button-primary-hover`), not nested (`button-primary.hover`)

---

## Mode 4: Sketch — Quick Throwaway Mockups

Use when the user wants to **see a design direction before committing** — exploring UI/UX ideas as disposable HTML mockups. 2-3 variants to compare.

### Core Method
```
intake → variants → head-to-head → pick winner (or iterate)
```

### Intake
Get three things (one at a time):
1. **Feel** — "What should this feel like? Adjectives, emotions?"
2. **References** — "What apps, sites capture the feel?"
3. **Core action** — "Single most important thing a user does on this screen?"

### Variants (2-3)
Each variant takes a different **design stance**, not different pixel values. Good axes:
- **Density**: compact / airy / ultra-dense
- **Emphasis**: content-first / action-first / tool-first
- **Aesthetic**: editorial / utilitarian / playful
- **Layout**: single-column / sidebar / split-pane

Each variant = one self-contained HTML file. Use system fonts or one Google Font. Tailwind via CDN is fine. Realistic fake content, not Lorem ipsum.

### Verification
```bash
browser_navigate(url="file://$(pwd)/sketches/001-calm-editorial/index.html")
browser_vision(question="How does this look? Any layout bugs?")
```

### Variant README
Each answers: design stance, key choices (layout, typography, color, interaction), trade-offs.

### Head-to-Head Comparison
After all variants built, present comparison table with opinionated recommendation.

---

## Design Anti-Patterns (All Modes)

Avoid:
- Aggressive gradient backgrounds
- Glassmorphism by default
- Emoji unless the brand uses them
- Generic SaaS cards with icons everywhere
- Left-border accent callout cards
- Fake dashboards with arbitrary numbers
- Stock-photo hero sections
- Oversized rounded rectangles as hierarchy substitute
- Rainbow palettes
- Vague labels like "Insights", "Growth", "Scale", "Optimize" without content
