---
description: Identify packages user hasn't used recently and may wish to remove
tags: [system, cleanup, packages, optimization, project, gitignored]
---

You are helping the user identify unused packages that could be removed to free up space.

## Process

1. **Check package installation dates**
   - For APT packages: `ls -lt /var/lib/dpkg/info/*.list | tail -50`
   - Check package access times if available

2. **Identify large packages**
   - List by size: `dpkg-query -W -f='${Installed-Size}\t${Package}\n' | sort -rn | head -30`
   - Focus on large packages that might be unused

3. **Check Flatpak packages**
   - List Flatpaks: `flatpak list --app`
   - Check Flatpak size: `flatpak list --app --columns=name,application,size`
   - Suggest running: `flatpak uninstall --unused` to remove unused runtimes

4. **Check Snap packages**
   - List snaps: `snap list`
   - Check snap disk usage: `du -sh /var/lib/snapd/snaps`
   - Identify old snap revisions: `snap list --all | grep disabled`
   - Suggest: `snap remove --purge <old-revision>`

5. **Identify orphaned packages (APT)**
   - Find orphaned packages: `deborphan`
   - Check apt autoremove suggestions: `apt autoremove --dry-run`

6. **Check for development packages**
   - List `-dev` packages: `dpkg -l | grep -E "^ii.*-dev"`
   - Ask user if they're actively developing and need these

7. **Review by category**
   - Games (if user doesn't game)
   - Old kernels: `dpkg -l | grep linux-image`
   - Language packs not needed
   - Documentation packages (`-doc` suffix)

8. **Present findings to user**
   - Group by category and size
   - Estimate space that could be freed
   - Ask user to confirm before suggesting removal

## Output

Provide a report showing:
- Total number of installed packages
- Potentially unused packages by category
- Space that could be freed
- Safe removal suggestions
- Warning about packages to NOT remove (dependencies)
