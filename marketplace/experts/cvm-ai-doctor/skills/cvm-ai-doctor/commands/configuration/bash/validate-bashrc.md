# Bashrc Validation

You are helping the user validate their .bashrc configuration for syntax errors, issues, and best practices.

## Your tasks:

1. **Locate bashrc files:**
   - Check `~/.bashrc`
   - Check `~/.bash_profile`
   - Check `~/.profile`
   - Check `/etc/bash.bashrc` (system-wide)
   - Note which files exist and their sizes

2. **Syntax validation:**
   - Test bashrc syntax: `bash -n ~/.bashrc`
   - If errors are found, report the line numbers and error messages
   - Check for common syntax issues:
     - Unclosed quotes
     - Unmatched brackets
     - Missing 'fi', 'done', 'esac' keywords

3. **Source validation:**
   - Test if bashrc can be sourced without errors in a subshell:
     ```bash
     bash -c 'source ~/.bashrc && echo "Sourcing successful"'
     ```
   - Capture any error messages

4. **Check for common issues:**
   - Duplicate PATH entries:
     ```bash
     bash -c 'source ~/.bashrc; echo $PATH | tr ":" "\n" | sort | uniq -d'
     ```
   - Check for sourcing non-existent files:
     ```bash
     grep -n "source\|^\." ~/.bashrc | while read line; do
       # Extract and check if files exist
     done
     ```
   - Look for potentially problematic patterns:
     - Infinite loops
     - Commands that might hang (network calls without timeouts)
     - Unguarded recursive sourcing

5. **Check initialization order:**
   - Explain which files are loaded and in what order for:
     - Login shells
     - Non-login interactive shells
     - Non-interactive shells
   - Check if the proper guards are in place (e.g., checking for interactive shell)

6. **Performance analysis:**
   - Time how long bashrc takes to load:
     ```bash
     time bash -c 'source ~/.bashrc; exit'
     ```
   - If it takes more than 0.5 seconds, identify potential slow sections:
     - Look for commands that might be slow (network calls, heavy computations)
     - Check for unnecessary repeated operations

7. **Check for security issues:**
   - World-writable bashrc: `ls -la ~/.bashrc`
   - Suspicious commands (downloads, eval with user input, etc.)
   - Sourcing files from world-writable directories

8. **Validate environment manager initialization:**
   - Check if environment managers are properly initialized:
     - pyenv: `grep "pyenv init" ~/.bashrc`
     - conda: `grep "conda initialize" ~/.bashrc`
     - nvm: `grep "nvm.sh" ~/.bashrc`
     - rbenv: `grep "rbenv init" ~/.bashrc`
     - sdkman: `grep "sdkman-init.sh" ~/.bashrc`
   - Verify they're in the correct order (PATH modifications should come after system PATH is set)

9. **Check for best practices:**
   - Interactive shell guard at the top:
     ```bash
     [[ $- != *i* ]] && return
     ```
   - Proper PATH modification (appending/prepending, not replacing)
   - Using `command -v` instead of `which`
   - Proper quoting of variables

10. **Report findings:**
    - Summary of validation results (PASS/FAIL)
    - List of any errors or warnings
    - Performance metrics
    - Recommendations:
      - Fixes for any syntax errors
      - Optimization suggestions if slow
      - Security improvements if needed
      - Best practice improvements
    - If bashrc is missing, offer to create a basic one

## Important notes:
- Don't modify the bashrc unless explicitly asked
- Be careful when testing - use subshells to avoid affecting the current environment
- Distinguish between critical errors and style suggestions
- Consider that some "issues" might be intentional for the user's workflow
