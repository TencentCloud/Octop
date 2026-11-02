# Manually Update YADM

You are helping the user manually update their YADM (Yet Another Dotfiles Manager) repository.

## Task

1. First, check the current status of the YADM repository:
   ```bash
   yadm status
   ```

2. Show the user what files have been modified:
   ```bash
   yadm diff
   ```

3. Ask the user which files they want to add to the commit. If they want to add all changes, use:
   ```bash
   yadm add -u
   ```

   Or for specific files:
   ```bash
   yadm add <file1> <file2> ...
   ```

4. Show the staged changes:
   ```bash
   yadm status
   ```

5. Ask the user for a commit message, then create the commit:
   ```bash
   yadm commit -m "user's commit message"
   ```

6. Push the changes to the remote repository:
   ```bash
   yadm push
   ```

7. Confirm the update was successful and show the final status.

## Notes

- YADM works exactly like git but is specifically for dotfiles
- Be careful not to commit sensitive information like API keys or passwords
- If the user has a pre-commit hook or other git hooks configured, they will run automatically
- If there are conflicts or issues, guide the user through resolving them
