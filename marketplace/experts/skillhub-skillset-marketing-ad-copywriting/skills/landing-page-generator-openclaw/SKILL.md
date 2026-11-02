---
name: landing-page-generator
description: Generate high-converting, mobile-responsive landing pages from a brief. Use when building landing pages, sales pages, or marketing pages for clients.
argument-hint: "[product-or-service-description]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Landing Page Generator

Generate complete, high-converting landing pages from a product/service brief. Outputs production-ready HTML/CSS that's mobile-responsive and optimized for conversions.

## How to Use

```
/landing-page-generator "SaaS project management tool for remote teams, $29/mo, free trial"
/landing-page-generator brief.txt
/landing-page-generator "Freelance web developer portfolio — book a call CTA"
```

Provide as much context as possible:
- What the product/service is
- Target audience
- Primary CTA (sign up, buy, book a call, download)
- Pricing (if applicable)
- Key features/benefits
- Brand colors (optional, defaults to professional blue/dark theme)

## Page Generation Process

### Step 1: Analyze the Brief

Extract:
- **Product type**: SaaS, physical product, service, portfolio, lead magnet, event
- **Target audience**: Who is this for?
- **Primary CTA**: What action should visitors take?
- **Value proposition**: Why should they care?
- **Tone**: Professional, casual, bold, minimal, luxurious

### Step 2: Select Page Template

Based on product type:

| Type | Sections | Typical Length |
|------|----------|---------------|
| SaaS | Hero, Features, How It Works, Pricing, Testimonials, FAQ, CTA | Long |
| Service | Hero, Services, Process, Portfolio, Testimonials, CTA | Medium |
| Portfolio | Hero, Work Samples, About, Services, Contact | Medium |
| Lead Magnet | Hero, Benefits, Social Proof, Form, CTA | Short |
| E-commerce | Hero, Product Features, Gallery, Reviews, Buy CTA | Medium |
| Event | Hero, Speakers/Details, Schedule, Tickets, FAQ | Medium |

### Step 3: Generate the Page

Create a single self-contained HTML file with embedded CSS. No external dependencies except Google Fonts.

**Required sections** (adapt to product type):

#### Hero Section
```
- Headline: Clear value proposition (max 10 words)
- Subheadline: Supporting detail (max 25 words)
- CTA button: High-contrast, action-oriented text ("Start Free Trial", not "Submit")
- Optional: Hero image placeholder or background
- Optional: Social proof badge ("Trusted by 10,000+ teams")
```

#### Features/Benefits
```
- 3-4 feature cards with icons (use Unicode/emoji icons)
- Each card: Icon + Feature name + 1-2 sentence benefit (focus on outcome, not feature)
- Grid layout: 3 columns on desktop, 1 on mobile
```

#### Social Proof
```
- 2-3 testimonial cards with:
  - Quote text
  - Name and title/company
  - Star rating (if applicable)
- Optional: Logo bar of client/partner logos (placeholder boxes with company names)
```

#### How It Works (if applicable)
```
- 3-step process with numbered steps
- Step title + brief description
- Visual connector between steps
```

#### Pricing (if applicable)
```
- 1-3 pricing tiers in card format
- Highlight the recommended tier
- Feature comparison list
- CTA button on each tier
```

#### FAQ
```
- 4-6 common questions
- Accordion-style (click to expand) using pure CSS/HTML <details>
```

#### Final CTA
```
- Repeat the primary CTA with urgency
- Different angle from hero (address remaining objections)
- Strong contrasting background
```

### Step 4: Design System

Apply these design principles:

**Typography**:
- Font: `Inter` from Google Fonts (clean, modern, high readability)
- Heading scale: 3rem, 2rem, 1.5rem, 1.25rem
- Body: 1rem / 1.6 line-height
- Max line width: 65ch for readability

**Colors** (default, override with brand colors if provided):
```css
--primary: #2563eb;        /* Blue - CTAs, links */
--primary-dark: #1d4ed8;   /* Hover state */
--bg: #ffffff;             /* Background */
--bg-alt: #f8fafc;         /* Alternating section bg */
--text: #1e293b;           /* Body text */
--text-light: #64748b;     /* Secondary text */
--accent: #f59e0b;         /* Highlights, badges */
```

**Layout**:
- Max width: 1200px, centered
- Section padding: 80px vertical (48px on mobile)
- Consistent spacing scale: 4, 8, 16, 24, 32, 48, 64, 80px

**Responsive breakpoints**:
- Desktop: 1024px+
- Tablet: 768px - 1023px
- Mobile: < 768px

### Step 5: Conversion Optimization

Apply these conversion principles to the generated page:

1. **Above the fold**: Headline + CTA visible without scrolling
2. **Single CTA focus**: One primary action, repeated 2-3 times throughout
3. **Contrast ratio**: CTA buttons must have WCAG AA contrast (4.5:1 minimum)
4. **Loading speed**: No external JS, minimal CSS, no images (placeholders only)
5. **Scannability**: Users should understand the offer in 5 seconds
6. **Objection handling**: FAQ and testimonials address common concerns
7. **Urgency/scarcity**: Optional — only if authentic ("Limited beta spots", not fake countdowns)

### Step 6: Output

Save to `output/landing-page/`:

```
output/landing-page/
  index.html          # Complete self-contained page
  README.md           # Customization guide for the client
```

**`README.md`** includes:
- How to customize colors (CSS variables at top of file)
- How to replace placeholder content
- How to add real images
- How to connect forms to their email service
- How to deploy (Netlify drag-and-drop, GitHub Pages, any static host)

### Step 7: Present to User

Show:
1. Brief summary of what was generated
2. Key design decisions made
3. File location
4. Suggestions for what the client should customize (images, testimonials, specific copy)

## Quality Standards

- [ ] Page loads with no external dependencies except Google Fonts
- [ ] Fully responsive at 320px, 768px, and 1200px widths
- [ ] All CTA buttons have hover states
- [ ] Color contrast meets WCAG AA
- [ ] Page has proper `<meta>` viewport tag
- [ ] Semantic HTML (`<header>`, `<main>`, `<section>`, `<footer>`)
- [ ] No horizontal scroll at any breakpoint
- [ ] FAQ sections are interactive (expand/collapse)
- [ ] Total HTML file size under 50KB
