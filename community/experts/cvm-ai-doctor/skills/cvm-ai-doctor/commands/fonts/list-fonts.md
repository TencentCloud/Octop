---
description: List installed fonts and offer to install additional fonts
tags: [fonts, typography, system, customization, project, gitignored]
---

You are helping the user review their installed fonts and install additional ones if requested.

## Process

1. **List currently installed fonts**
   - System fonts: `fc-list | cut -d: -f2 | sort -u | wc -l` (count)
   - Show font families: `fc-list : family | sort -u`
   - List font directories:
     - System: `/usr/share/fonts/`
     - User: `~/.local/share/fonts/`

2. **Categorize installed fonts**
   - Serif fonts
   - Sans-serif fonts
   - Monospace/coding fonts
   - Display/decorative fonts
   - Icon fonts

3. **Check for common font packages**
   - `dpkg -l | grep -E "fonts-|ttf-"`
   - Common packages:
     - `fonts-liberation`
     - `fonts-noto`
     - `fonts-roboto`
     - `ttf-mscorefonts-installer`
     - `fonts-powerline`

4. **Suggest useful font additions**

   **For coding:**
   - Fira Code (ligatures)
   - JetBrains Mono
   - Cascadia Code
   - Victor Mono
   - Source Code Pro

   **For design:**
   - Inter
   - Poppins
   - Montserrat
   - Raleway

   **System fonts:**
   - Noto fonts (comprehensive Unicode)
   - Liberation fonts (MS Office compatible)

   **Icons:**
   - Font Awesome
   - Material Design Icons
   - Nerd Fonts

5. **Installation methods**
   - APT: `sudo apt install fonts-<name>`
   - Manual installation:
     ```bash
     mkdir -p ~/.local/share/fonts
     # Copy font files to directory
     fc-cache -fv
     ```
   - Google Fonts downloader (see separate command)

6. **Test font installation**
   - Refresh font cache: `fc-cache -fv`
   - Verify font: `fc-list | grep -i <font-name>`
   - Show sample: `fc-match <font-name>`

## Output

Provide a report showing:
- Total number of installed font families
- List of installed fonts by category
- Missing commonly-used fonts
- Suggested fonts to install based on use case
- Installation commands
