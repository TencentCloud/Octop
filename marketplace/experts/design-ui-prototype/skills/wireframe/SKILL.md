---
name: wireframe
description: "Create wireframes and user flows. Use when sketching page layouts in ASCII/SVG, mapping flows, or exporting to HTML."
version: "3.4.0"
author: BytesAgain
homepage: https://bytesagain.com
source: https://github.com/bytesagain/ai-skills
tags:
  - wireframe
  - design
  - ascii
  - svg
  - ux
  - flowchart
---

# Wireframe

Generate wireframes, component sketches, and user flow diagrams for UI design.

## Commands

### page

Generate a full-page wireframe in ASCII or SVG format.

```bash
bash scripts/script.sh page --sections "header,hero,features,cta,footer" --format svg --output wireframe.svg
```

### component

Generate a wireframe for a single UI component (form, card, nav, table, etc).

```bash
bash scripts/script.sh component --type card --fields "image,title,text,button" --output card.svg
```

### flow

Generate a user flow diagram showing page transitions and decision points.

```bash
bash scripts/script.sh flow --steps "login,dashboard,settings,logout" --decisions "auth:yes/no" --output flow.svg
```

### annotate

Add numbered annotations and notes to an existing SVG wireframe.

```bash
bash scripts/script.sh annotate --input wireframe.svg --notes "1:Logo area,2:Search bar,3:Main content" --output annotated.svg
```

### export

Export a wireframe to standalone HTML with inline styles.

```bash
bash scripts/script.sh export --input wireframe.svg --format html --output wireframe.html
```

### template

Generate a wireframe from a built-in page template (landing, dashboard, blog, ecommerce, etc).

```bash
bash scripts/script.sh template --name landing --format ascii
```

## Output

- `page`: ASCII wireframe to stdout or SVG file to disk
- `component`: SVG file with component wireframe
- `flow`: SVG flowchart with boxes and arrows
- `annotate`: SVG file with annotation markers and legend
- `export`: Standalone HTML file with embedded wireframe
- `template`: Wireframe output in chosen format


## Requirements
- bash 4+

## Feedback

https://bytesagain.com/feedback/

---

Powered by BytesAgain | bytesagain.com
