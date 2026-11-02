---
description: Set up rclone for cloud storage management
tags: [cloud, rclone, setup, backup, project, gitignored]
---

You are helping the user set up rclone for cloud storage management.

## Process

1. **Check if rclone is installed**
   - Run `rclone version` to check installation
   - If not installed, install using: `sudo apt install rclone` or download from rclone.org

2. **Check existing remotes**
   - Run `rclone listremotes` to see configured remotes
   - Run `rclone config file` to show config file location

3. **Configure new remotes if needed**
   - Run `rclone config` for interactive setup
   - Guide user through:
     - Choosing storage type (S3, B2, Google Drive, etc.)
     - Entering credentials
     - Testing connection

4. **Validate existing remotes**
   - For each remote, test with: `rclone lsd <remote>:`
   - Verify access and permissions

5. **Optimization suggestions**
   - Suggest setting up encrypted remotes for sensitive data
   - Recommend bandwidth limits if needed: `--bwlimit`
   - Suggest useful flags for backups: `--transfers`, `--checkers`
   - Offer to create wrapper scripts for common operations

## Output

Provide a summary showing:
- rclone version
- List of configured remotes with types
- Validation status for each remote
- Suggested next steps or optimizations
