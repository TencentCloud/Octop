---
source: |
  来源：Tailwind CSS / 行业最佳实践
  URL: https://www.tailwindcss.cn/
date: 2026-04-25
---

# Tailwind CSS Browser Support

## Supported Browsers (v3.0+)
- Chrome (latest stable)
- Firefox (latest stable)
- Edge (latest stable)
- Safari (latest stable)

## NOT Supported
- Internet Explorer 11 (IE11) - Not supported at all

## Bleeding-Edge Features
Some features may have limited support:
- :focus-visible pseudo-class
- backdrop-filter utilities
- These can be avoided if browser support is a concern

## Vendor Prefixes
- Many CSS properties require vendor prefixes (e.g., -webkit-background-clip: text)
- Tailwind CLI adds prefixes automatically
- For PostCSS: Use Autoprefixer plugin
  npm install -D autoprefixer
  # Add to end of PostCSS plugins list

## H5 Mobile Browser Support Notes
For Chinese market H5 development:
- WeChat built-in browser (X5内核) - generally good modern browser support
- UC Browser - supports most modern CSS but may need Autoprefixer
- Baidu Browser - similar to Chrome/Chromium
- Safari iOS - full support for Tailwind features
- Android default browser - varies by Android version

## Recommendation for H5
- Always use Autoprefixer for production
- Test on WeChat/X5内核 - common in China
- Use Can I Use (caniuse.com) to check specific CSS feature support
