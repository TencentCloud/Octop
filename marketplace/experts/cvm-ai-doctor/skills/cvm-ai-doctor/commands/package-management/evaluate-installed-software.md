---
description: Evaluate installed software and suggest complementary CLIs or GUIs
tags: [system, audit, software, recommendations, optimization, project, gitignored]
---

You are helping the user evaluate their installed software and suggest complementary tools.

## Process

1. **Inventory installed software**
   - APT packages: `apt list --installed | wc -l`
   - Snap packages: `snap list`
   - Flatpak packages: `flatpak list`
   - pip packages: `pip list`
   - Manually installed in `~/programs`

2. **Categorize software**
   - Development tools
   - Media/graphics applications
   - System utilities
   - Communication tools
   - AI/ML tools
   - Backup/storage tools

3. **Identify gaps and complementary tools**
   - For each category, suggest:
     - Missing CLIs that complement existing GUIs
     - Missing GUIs that complement existing CLIs
     - Alternative tools that might be better suited
     - Modern replacements for outdated tools

4. **Examples of complementary suggestions**
   - If `docker` installed, suggest `lazydocker` GUI
   - If `git` installed, suggest `gitui` or `lazygit`
   - If `code` (VS Code) installed, suggest useful extensions
   - If media editing tools installed, suggest codec packages
   - If Python installed, suggest `pipx` for isolated CLI tools

5. **Present recommendations**
   - Group by category
   - Explain the benefit of each suggestion
   - Prioritize based on user's existing software patterns

## Output

Provide a report showing:
- Summary of installed software by category
- List of recommended complementary tools
- Brief explanation of why each tool would be useful
- Installation commands for suggested tools
