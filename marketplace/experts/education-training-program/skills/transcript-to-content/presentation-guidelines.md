# Professional Presentation Guidelines

## Overview

Create professional, clean presentations that communicate training content clearly and effectively. These guidelines support creating presentations for any organization with customizable branding.

## Presentation Structure

### Standard Slide Deck Structure (12 slides max by default)

1. **Title Slide** - Topic introduction with metadata
2. **Definition/Overview** - What is the concept?
3. **Step-by-Step Content** - Core instructional slides (typically 4-6 steps)
4. **Critical Success Factors** - Key principles for effectiveness
5. **Common Pitfalls** - Mistakes to avoid
6. **Key Takeaways** - Summary checklist
7. **Closing Slide** - Final thought and branding

## Design Standards

### Visual Style

**Clean, Professional Design:**
- Clear grid systems
- Strong typography hierarchy
- Minimal decoration
- Ample white space
- Geometric accents (lines, simple shapes) used sparingly

**Prohibited Elements:**
- Excessive rounded corners
- Heavy shadows or 3D effects
- CSS animations or transitions (for HTML slides)
- Inline SVG code (use image files instead)
- Cluttered or busy layouts

### Branding Integration

**Logo Placement:**
- Content slides: Top-right corner (120-140px width)
- Title/Closing slides: Top-left or top-right (180-200px width)
- Always use absolute paths in HTML

**Brand Colors:**
- Ask user for primary brand color if not provided
- Use brand color for: header accents, key metrics, highlights, chart elements
- Maintain 60-30-10 rule: 60% neutral, 30% secondary, 10% brand accent

**Typography:**
- Use professional web fonts (Inter, Roboto, Open Sans, Montserrat)
- Maintain clear hierarchy with size and weight
- Ensure readability with sufficient contrast

### Color Application

**Recommended Neutral Palette:**
- Background: `#F2F2F2` or `#FFFFFF` (light grey or white)
- Text: `#1A1A1A` or `#2C2C2C` (near black)
- Secondary text: `#333333`, `#555555`, `#666666`
- Dark panels: `#1A1A1A` or `#2C2C2C` (for contrast sections)

**Color Usage Rules:**
- Use at most 2-3 colors per slide
- Ensure sufficient contrast for readability (WCAG AA minimum)
- Apply colors consistently throughout presentation
- Reserve brand color for emphasis and key information

### Typography Hierarchy

**Recommended Sizes:**
- Title slide main heading: 72-96px, weight 900
- Slide headers: 42-48px, weight 700-900
- Body text: 18-24px, weight 400-500
- Labels/captions: 14-18px, weight 600-700
- Large decorative numbers: 180-240px, weight 900

## Layout Patterns

### Title Slide Layout
- Large title (72-96px)
- Subtitle or description
- Metadata (module info, date, presenter)
- Optional accent bar or geometric element
- Logo placement
- Clean, uncluttered design

### Content Slide Layouts

**Three-Column Grid:**
- Column 1: Large step number or icon
- Column 2: Main content (instructions, metrics)
- Column 3: Insight/example panel (optional contrast background)

**Two-Column Split:**
- Left: Logic/formulas/steps
- Right: Examples/calculations or visual element

**Full-Width with Sections:**
- Header with accent underline
- Multiple content sections with clear hierarchy
- Visual dividers between sections

### Data Visualization

**Chart Guidelines:**
- Use Chart.js or similar libraries for standard charts
- Apply brand color for primary data
- Use neutral colors for secondary data
- Include clear labels and legends
- Ensure charts are readable at presentation size

**Example HTML structure:**
```html
<div style="height: 200px; max-width: 600px;">
    <canvas id="myChart"></canvas>
</div>
```

## Content Guidelines

### Writing Style

- **Imperative voice:** "Navigate to...", "Click...", "Set..."
- **Concise bullets:** Maximum 3-4 main points per slide
- **Clear hierarchy:** Use bold for emphasis, not decoration
- **Action-oriented:** Focus on what to do, not just what to know

### Information Density

- **Title slide:** Minimal text, strong visual presence
- **Content slides:** Balanced text and white space (aim for 40% white space)
- **Summary slides:** Checklist format with check marks (✓) or bullets

### Critical Elements to Include

1. **Step Numbers:** Large, prominent, consistent styling
2. **Action Items:** Clear, numbered lists with arrows (→) or bullets
3. **Warnings/Alerts:** Highlighted boxes with distinct styling
4. **Examples:** Real scenarios in contrasting panels
5. **Takeaways:** Summarized as actionable checklist items

## Technical Requirements (for HTML Slides)

### HTML Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Slide Title]</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
    <style>
        /* Styles here */
    </style>
</head>
<body>
    <div class="slide-container">
        <!-- Content here -->
    </div>
</body>
</html>
```

### Critical CSS Rules

**Slide Container:**
```css
.slide-container {
    width: 1280px;
    min-height: 720px;
    background-color: #F2F2F2;
    position: relative;
    overflow: hidden;
    padding: 80px 100px 60px;
    display: flex;
    flex-direction: column;
}
```

**Key Constraints:**
- Use `min-height` not `height` to prevent overflow
- Avoid excessive `padding-bottom` (can cause rendering issues)
- Use `padding-top` for vertical spacing
- Minimize CSS on body tag
- Avoid `position: absolute` for main content containers

## Workflow

1. **Gather brand assets** - Logo, colors, fonts (if provided by user)
2. **Initialize presentation** using `slide_initialize` tool
3. **Create outline** with all slide IDs and summaries
4. **Copy assets** to project directory (logo, images)
5. **Edit slides one by one** using `slide_edit` tool
6. **Present** using `slide_present` tool when complete
7. **Export to PDF** using `manus-export-slides` utility if requested

## Quality Checklist

Before presenting, verify:
- [ ] Logo appears on all slides (if provided)
- [ ] Brand colors used consistently
- [ ] All slides fit within 720px height
- [ ] Typography hierarchy is clear
- [ ] No prohibited design elements used
- [ ] Content is factual and based on source material
- [ ] Charts and visualizations are properly labeled
- [ ] Sufficient white space and readability
- [ ] Consistent styling across all slides
