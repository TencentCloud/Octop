---
description: Set up or validate Backblaze B2 CLI configuration
tags: [cloud, b2, backblaze, setup, validation, project, gitignored]
---

You are helping the user set up or validate their Backblaze B2 CLI configuration.

## Process

1. **Check if B2 CLI is installed**
   - Run `b2 version` to check installation
   - If not installed, install using: `pip3 install b2 --upgrade --user` or `sudo apt install backblaze-b2`

2. **Check existing authorization**
   - Run `b2 get-account-info` to see if already authorized
   - Check `~/.b2_account_info` if it exists

3. **Validate configuration**
   - If authorized, test by listing buckets: `b2 list-buckets`
   - Verify account ID and key are working

4. **Configure if needed**
   - If not configured or user wants to update:
     - Ask user for Application Key ID and Application Key
     - Run `b2 authorize-account <keyID> <applicationKey>`
     - Alternatively, use `b2 clear-account` first if re-authorizing

5. **Additional setup**
   - Show available buckets: `b2 list-buckets`
   - Suggest setting up lifecycle rules if doing backups
   - Recommend testing upload/download with a small file

## Output

Provide a summary showing:
- B2 CLI version
- Authorization status
- Account ID (if authorized)
- List of buckets (if any)
- Any recommendations for optimization
