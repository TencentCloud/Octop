---
description: Install Google Fonts provided by the user
tags: [fonts, google-fonts, typography, installation, project, gitignored]
---

You are helping the user install Google Fonts by name.

## Process

1. **Get font names from user**
   - Ask user which Google Fonts they want to install
   - Accept multiple font names

2. **Choose installation method**

   **Method 1: Using google-font-installer (if available)**
   - Install tool: `pip install gftools`
   - Download font: `gftools download-family "Font Name"`

   **Method 2: Using font-downloader**
   - Install: `sudo apt install font-manager`
   - Or use: `pip install font-downloader`

   **Method 3: Manual download**
   - Download from: `https://fonts.google.com/`
   - Or use GitHub: `https://github.com/google/fonts/tree/main/`

3. **Download fonts**
   - For each font name:
     - Convert name to lowercase with dashes (e.g., "Roboto Mono" → "roboto-mono")
     - Download from: `https://fonts.google.com/download?family=Font+Name`
     - Or clone specific font: `git clone https://github.com/google/fonts.git --depth 1 --filter=blob:none --sparse && cd fonts && git sparse-checkout set ofl/<font-name>`

4. **Install fonts**
   - Create user font directory: `mkdir -p ~/.local/share/fonts/google-fonts`
   - Extract and copy font files:
     ```bash
     unzip <font>.zip -d ~/.local/share/fonts/google-fonts/<font-name>/
     ```
   - Only copy .ttf and .otf files

5. **Update font cache**
   - Run: `fc-cache -fv`
   - Verify installation: `fc-list | grep -i "<font-name>"`

6. **Provide usage examples**
   - Show how to use in applications
   - Show how to set as system font
   - Show how to use in CSS/web design

## Example Workflow

```bash
# Example: Installing "Roboto" and "Open Sans"
mkdir -p ~/.local/share/fonts/google-fonts
cd /tmp

# Download Roboto
wget "https://fonts.google.com/download?family=Roboto" -O roboto.zip
unzip roboto.zip -d ~/.local/share/fonts/google-fonts/roboto/

# Download Open Sans
wget "https://fonts.google.com/download?family=Open+Sans" -O open-sans.zip
unzip open-sans.zip -d ~/.local/share/fonts/google-fonts/open-sans/

# Update cache
fc-cache -fv

# Verify
fc-list | grep -i "roboto\|open sans"
```

## Output

Provide a summary showing:
- Fonts requested by user
- Download and installation status for each
- Installation location
- Verification that fonts are available
- Usage examples
