---
name: ui-design
model: standard
version: 1.0.0
description: >
  Comprehensive UI design skill covering fundamentals, patterns, and anti-patterns.
  Layout, typography, color, spacing, accessibility, motion, and component design.
  Use when building any web interface, reviewing design quality, or creating distinctive UIs.
tags: [ui, design, frontend, accessibility, typography, color, layout, motion]
---

# UI Design Fundamentals

The definitive guide for building production-grade web interfaces. Covers the full stack of design decisions from layout to motion.

## WHEN To Use

- Designing new UI components or pages
- Building landing pages, dashboards, or applications
- Reviewing code for design quality
- Creating distinctive interfaces that avoid generic aesthetics
- Implementing accessibility requirements

## KEYWORDS

ui design, web design, layout, typography, color palette, spacing, visual hierarchy, responsive design, accessibility, motion design, component design, design tokens, frontend, css, tailwind

---

## Design Philosophy

### The 80/20 of Design Quality

| Factor | Impact | Time Investment |
|--------|--------|-----------------|
| **Typography** | 40% | Choose 1-2 fonts well |
| **Spacing** | 25% | Use consistent scale |
| **Color** | 20% | Limit palette, ensure contrast |
| **Everything else** | 15% | Shadows, borders, motion |

Focus on typography and spacing first. They're 65% of perceived quality.

### Commit to a Direction

Mediocrity is forgettable. Pick an extreme:

| Direction | Characteristics | Use When |
|-----------|-----------------|----------|
| **Brutally Minimal** | Stark, essential, nothing extra | Developer tools, productivity |
| **Luxury/Refined** | Premium, subtle elegance | High-end products, fashion |
| **Playful** | Fun, bright, approachable | Consumer apps, games |
| **Editorial** | Type-forward, grid-based | Content sites, magazines |
| **Industrial** | Function-forward, robust | B2B, enterprise |

---

## Layout

### Grid vs Flexbox Decision

| Layout Need | Tool | Why |
|-------------|------|-----|
| Page-level structure | CSS Grid (`grid-template-areas`) | Named regions, explicit control |
| Navigation bars | Flexbox | Single-axis, `gap` spacing |
| Card grids | Grid (`auto-fill`/`auto-fit`) | Responsive without media queries |
| Centering | Grid (`place-items: center`) | Shortest, most reliable |
| Sidebar + content | Grid (`250px 1fr`) | Fixed + fluid |
| Stacking/overlaps | Grid + `grid-area: 1/1` | No `position: absolute` needed |

### Container Strategy

```css
/* Standard content width */
.container {
  width: 100%;
  max-width: 1280px;
  margin-inline: auto;
  padding-inline: clamp(1rem, 5vw, 3rem);
}

/* Full-bleed with contained content */
.full-bleed {
  width: 100vw;
  margin-left: calc(50% - 50vw);
}
```

### Common Layout Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Mixing container widths | Inconsistent alignment | Use single `max-w-*` value |
| Content behind fixed navbar | Hidden content | Add `pt-[navbar-height]` |
| No mobile padding | Edge-to-edge text | Add `px-4` minimum |
| Centered everything | Weak hierarchy | Left-align body text |

---

## Typography

Typography carries 90% of a design's personality.

### Font Pairing by Context

| Context | Display Font | Body Font | Example |
|---------|--------------|-----------|---------|
| Editorial | High-contrast serif | Neutral humanist | Playfair + Source Sans |
| SaaS | Geometric sans | Matching sans | DM Sans + DM Mono |
| Luxury | Thin modern serif | Elegant sans | Cormorant + Jost |
| Developer | Monospace display | Monospace body | JetBrains Mono + IBM Plex |
| Playful | Rounded/quirky | Clean readable | Nunito + Outfit |

### Type Scale (1.25 ratio)

```css
--text-xs: 0.64rem;   /* 10px - captions */
--text-sm: 0.8rem;    /* 13px - secondary */
--text-base: 1rem;    /* 16px - body */
--text-lg: 1.25rem;   /* 20px - lead */
--text-xl: 1.563rem;  /* 25px - h4 */
--text-2xl: 1.953rem; /* 31px - h3 */
--text-3xl: 2.441rem; /* 39px - h2 */
--text-4xl: 3.052rem; /* 49px - h1 */
```

### Typography Rules

| Rule | Value | Why |
|------|-------|-----|
| Minimum body size | 16px | Below is hard to read |
| Body line-height | 1.5-1.75 | Improves readability |
| Heading line-height | 1.1-1.2 | Tighter for large text |
| Line length | 60-75 characters | Optimal reading |
| Paragraph spacing | 1.5em | Clear separation |

### Typography Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| System fonts only | Generic look | Use Google Fonts or variable fonts |
| Too many fonts | Visual chaos | Max 2 families |
| Weak weight contrast | Poor hierarchy | Bold headings (600+), regular body |
| Long lines | Hard to read | Add `max-w-prose` (65ch) |

---

## Color

### Building a Palette

Every palette needs five functional roles:

| Role | Purpose | Usage |
|------|---------|-------|
| **Primary** | Brand identity | Buttons, links, active states |
| **Neutral** | Text, backgrounds | Body text, cards, dividers |
| **Accent** | Secondary actions | Tags, badges, highlights |
| **Semantic** | Feedback | Success/warning/error states |
| **Surface** | Layered backgrounds | Cards, modals, overlays |

### Surface Layering (Dark Mode)

Create depth through lightness, not shadows:

```css
:root {
  --surface-0: hsl(220 15% 8%);   /* page background */
  --surface-1: hsl(220 15% 12%);  /* card */
  --surface-2: hsl(220 15% 16%);  /* raised element */
  --surface-3: hsl(220 15% 20%);  /* popover/modal */
}
```

### Contrast Requirements (WCAG)

| Text Size | Minimum Ratio | Enhanced (AAA) |
|-----------|---------------|----------------|
| Normal text (<18px) | 4.5:1 | 7:1 |
| Large text (≥18px bold, ≥24px) | 3:1 | 4.5:1 |
| UI components | 3:1 | — |

### Color Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Purple gradient on white | "AI aesthetic" cliché | Use intentional brand colors |
| Low contrast text | Accessibility fail | Test with contrast checker |
| Color-only indicators | Colorblind users excluded | Add icons/text |
| Too many colors | Visual noise | 3-5 colors maximum |
| Light gray text on white | Unreadable | `slate-600` minimum |

---

## Spacing

### 8px Base Unit Scale

```css
--space-1: 0.25rem;  /* 4px - tight gaps */
--space-2: 0.5rem;   /* 8px - input padding */
--space-3: 0.75rem;  /* 12px - button padding */
--space-4: 1rem;     /* 16px - default spacing */
--space-6: 1.5rem;   /* 24px - section padding */
--space-8: 2rem;     /* 32px - section gaps */
--space-12: 3rem;    /* 48px - major breaks */
--space-16: 4rem;    /* 64px - page rhythm */
```

### Spacing Rules

| Rule | Implementation |
|------|----------------|
| Use `gap` not margins | `display: flex; gap: var(--space-4)` |
| Consistent padding | Same values on all cards/sections |
| More space between groups | Less space within groups (Gestalt) |
| No arbitrary values | Only use scale tokens |

### Spacing Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Arbitrary pixel values | Inconsistent rhythm | Use spacing scale only |
| Margin on children | Margin collapse bugs | Use `gap` on parent |
| Equal spacing everywhere | No visual grouping | More between, less within |
| Tight mobile padding | Cramped feeling | Minimum `p-4` on mobile |

---

## Visual Hierarchy

Guide the eye through deliberate contrast.

### Hierarchy Techniques

| Technique | How | Impact |
|-----------|-----|--------|
| **Size** | Hero 3-4x body | Immediate focal point |
| **Weight** | Bold headings, regular body | Scannability |
| **Color** | Primary vs muted | Information layers |
| **Space** | Isolation creates emphasis | Draws attention |
| **Position** | Top-left anchors reading | Natural flow |

### Card Hierarchy Pattern

```
Eyebrow  ← xs, uppercase, muted color
Title    ← xl, semibold, primary color
Body     ← base, secondary color, 1.6 line-height
Action   ← spaced apart, mt-4 minimum
```

---

## Responsive Design

### Breakpoint Strategy

| Breakpoint | Target | Key Changes |
|------------|--------|-------------|
| < 640px | Mobile | Single column, stacked nav, 44px touch targets |
| 640-1024px | Tablet | Two columns, collapsible sidebars |
| 1024-1440px | Desktop | Full layout, hover enabled |
| > 1440px | Wide | Max-width container, prevent ultra-wide lines |

### Fluid Techniques

```css
/* Fluid typography */
h1 { font-size: clamp(2rem, 1.5rem + 2.5vw, 3.5rem); }

/* Fluid spacing */
section { padding-block: clamp(2rem, 1rem + 4vw, 6rem); }

/* Intrinsic grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
  gap: var(--space-6);
}
```

### Responsive Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| No viewport meta | Broken mobile | Add `width=device-width` |
| Fixed widths | Overflow on mobile | Use `max-w-*` and `%` |
| Tiny touch targets | Frustrating taps | Minimum 44x44px |
| Hidden horizontal scroll | Broken layout | Test at 375px width |

---

## Accessibility

Accessibility is not optional.

### Critical Requirements

| Requirement | Implementation | Standard |
|-------------|----------------|----------|
| Color contrast | 4.5:1 normal, 3:1 large | WCAG 2.1 AA |
| Keyboard navigation | Tab order matches visual | WCAG 2.1.1 |
| Focus indicators | Visible `:focus-visible` ring | WCAG 2.4.7 |
| Semantic HTML | `<button>`, `<nav>`, `<main>` | WCAG 1.3.1 |
| Alt text | Descriptive for images | WCAG 1.1.1 |
| Motion safety | `prefers-reduced-motion` | WCAG 2.3.3 |
| Touch targets | 44×44px minimum | WCAG 2.5.8 |

### Focus Styles

```css
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Remove default only if custom exists */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Motion Safety

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Motion & Animation

Use motion to communicate, not decorate.

### Timing Guidelines

| Interaction | Duration | Easing |
|-------------|----------|--------|
| Button hover | 150ms | ease-out |
| Modal open | 250ms | ease-out |
| Modal close | 200ms | ease-in |
| Page transition | 300ms | ease-in-out |
| Stagger delay | 50-80ms per item | — |
| Micro-feedback | 100ms | ease-out |

### Staggered Entrance

```css
.item {
  opacity: 0;
  translate: 0 1rem;
  animation: reveal 0.5s ease-out forwards;
}
.item:nth-child(1) { animation-delay: 0ms; }
.item:nth-child(2) { animation-delay: 60ms; }
.item:nth-child(3) { animation-delay: 120ms; }

@keyframes reveal {
  to { opacity: 1; translate: 0 0; }
}
```

### Motion Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Animating width/height | Performance hit | Use `transform` only |
| > 500ms duration | Feels sluggish | 150-300ms for most |
| Motion everywhere | Overwhelming | Focus on entrances/exits |
| No reduced-motion | Accessibility fail | Always check preference |

---

## Component States

Every interactive element needs clear states.

| State | Visual Treatment |
|-------|------------------|
| **Default** | Base styling |
| **Hover** | Subtle background/shadow shift |
| **Active/Pressed** | Slight inset, reduced shadow |
| **Focus** | High-visibility ring |
| **Disabled** | 50% opacity, `not-allowed` cursor |
| **Loading** | Spinner or skeleton |

### Button Example

```css
.btn {
  transition: all 150ms ease-out;
}
.btn:hover {
  background: var(--color-primary-600);
}
.btn:active {
  transform: scale(0.98);
}
.btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

---

## Design Tokens Architecture

Structure tokens in three layers:

```css
/* Layer 1: Primitives */
--blue-500: oklch(0.55 0.2 250);
--gray-100: oklch(0.95 0.005 250);
--radius-md: 0.5rem;

/* Layer 2: Semantic */
--color-primary: var(--blue-500);
--color-surface: var(--gray-100);
--radius-button: var(--radius-md);

/* Layer 3: Component */
--btn-bg: var(--color-primary);
--btn-radius: var(--radius-button);
--btn-padding: var(--space-2) var(--space-4);
```

This allows theme switching by remapping Layer 2 only.

---

## Pre-Delivery Checklist

### Typography
- [ ] Intentional font pairing (not system defaults)
- [ ] Consistent type scale
- [ ] Line length ≤ 75 characters
- [ ] 16px minimum body text

### Color
- [ ] Cohesive palette (3-5 colors)
- [ ] WCAG contrast met (4.5:1 normal, 3:1 large)
- [ ] Semantic colors defined
- [ ] Dark mode tested (if applicable)

### Spacing
- [ ] Consistent rhythm using scale
- [ ] No arbitrary pixel values
- [ ] Proper mobile padding

### Hierarchy
- [ ] Clear visual flow
- [ ] Primary action obvious
- [ ] Information layered by importance

### Responsive
- [ ] Mobile tested (375px)
- [ ] No horizontal overflow
- [ ] Touch targets ≥ 44px

### Accessibility
- [ ] Keyboard navigable
- [ ] Focus visible
- [ ] Screen reader tested
- [ ] Motion-safe

### States
- [ ] Hover on all interactive elements
- [ ] Focus-visible on all focusable
- [ ] Loading states for async
- [ ] Error states for forms

### Performance
- [ ] Images optimized (WebP, srcset)
- [ ] Fonts subset
- [ ] Animations use `transform`/`opacity`

---

## NEVER Do

1. **NEVER skip contrast checking** — Test every text/background combination
2. **NEVER use color alone** — Always pair with icons/text for meaning
3. **NEVER remove focus outlines** — Unless replacing with visible alternative
4. **NEVER use arbitrary spacing** — Stick to the scale
5. **NEVER animate layout properties** — Only `transform` and `opacity`
6. **NEVER ignore reduced-motion** — Always check the preference
7. **NEVER center everything** — Left-align body text
8. **NEVER use tiny touch targets** — 44px minimum
9. **NEVER use low-contrast text** — `slate-600` minimum on white
10. **NEVER use generic system fonts** — Choose intentional typography

---

## Related Skills

- `ui-ux-pro-max` — Searchable design databases with CLI
- `frontend-design` — Creative aesthetics, avoiding "AI slop"
- `theme-factory` — Applying themes to artifacts
- `design-system-patterns` — Token architecture and theming
