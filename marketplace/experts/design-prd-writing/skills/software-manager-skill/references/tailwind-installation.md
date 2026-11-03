---
source: |
  来源：Tailwind CSS / 行业最佳实践
  URL: https://www.tailwindcss.cn/
date: 2026-04-25
---

# Tailwind CSS Installation Methods

## 1. CDN (Play CDN) - Quick Prototyping
- Simplest and fastest way to get started
- Add via script tag: <script src="https://cdn.tailwindcss.com"></script>
- Best for quick prototypes, not recommended for production

## 2. Tailwind CLI - Recommended for Most Projects
Steps:
1. Install via npm: npm install -D tailwindcss
2. Initialize: npx tailwindcss init
3. Configure tailwind.config.js with content paths:
   module.exports = {
     content: ["./src/**/*.{html,js}"],
     theme: { extend: {} },
     plugins: [],
   }
4. Add directives to CSS (input.css):
   @tailwind base;
   @tailwind components;
   @tailwind utilities;
5. Run build: npx tailwindcss -i ./src/input.css -o ./src/output.css --watch

## 3. PostCSS Integration - For Build Tools
- Integrate with webpack, Vite, Rollup via PostCSS
- Install: npm install -D tailwindcss postcss autoprefixer
- Configure postcss.config.js with tailwindcss and autoprefixer plugins
- Autoprefixer recommended for vendor prefixes automatically

## Key Notes for H5 Development
- Tailwind v3.x requires @tailwind base directive for transforms, filters, shadows
- Use responsive modifiers (sm:, md:, lg:, xl:) for mobile-first design
- JIT engine scans content for class names automatically
- No IE11 support in v3.0+
