# Check YADM Status

You are helping the user check the status of their YADM (Yet Another Dotfiles Manager) repository.

## Task

1. Check which files YADM is currently tracking:
   ```bash
   yadm list -a
   ```

2. Show the current repository status (modified, staged, untracked files):
   ```bash
   yadm status
   ```

3. Show recent commit history (last 10 commits):
   ```bash
   yadm log --oneline -10
   ```

4. Check if there are any unpushed commits:
   ```bash
   yadm log origin/main..HEAD --oneline
   ```
   (Note: Replace 'main' with the actual branch name if different, e.g., 'master')

5. Show which remote repository YADM is connected to:
   ```bash
   yadm remote -v
   ```

6. Summarize the findings for the user:
   - Total number of tracked files
   - Any uncommitted changes
   - Any unpushed commits
   - Current branch
   - Remote repository location

## Additional Checks (Optional)

If requested, you can also:
- Show files that have been modified: `yadm diff --name-only`
- Check for files that should be tracked but aren't: Look for common dotfiles in the home directory
- Verify the YADM repository is healthy: `yadm fsck`

## Notes

- YADM is a wrapper around git specifically for managing dotfiles
- All git commands work with yadm by replacing 'git' with 'yadm'
- The YADM repository is stored in `~/.local/share/yadm/repo.git`
