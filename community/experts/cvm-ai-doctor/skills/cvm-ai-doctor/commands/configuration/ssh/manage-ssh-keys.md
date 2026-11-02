---
description: Review installed SSH key pairs and delete old ones if desired
tags: [ssh, security, keys, configuration, project, gitignored]
---

You are helping the user manage their SSH keys.

## Process

1. **List SSH keys**
   - List keys in `~/.ssh/`: `ls -la ~/.ssh/`
   - Identify key pairs:
     - Private keys (no extension, or `.pem`)
     - Public keys (`.pub`)
     - Known hosts file
     - Config file

2. **Display public keys with details**
   - For each public key:
     ```bash
     for key in ~/.ssh/*.pub; do
       echo "=== $key ==="
       ssh-keygen -l -f "$key"
       echo ""
     done
     ```
   - Shows: key length, fingerprint, comment

3. **Check if keys are loaded in ssh-agent**
   - List loaded keys: `ssh-add -l`
   - If agent not running: `eval "$(ssh-agent -s)"`

4. **Identify key usage**
   - Check `~/.ssh/config` for key assignments
   - Ask user about each key:
     - Where is it used? (GitHub, servers, etc.)
     - Is it still needed?
     - When was it created?

5. **Check key security**
   - Verify key types (RSA, ED25519, etc.)
   - Check key lengths:
     - RSA: Minimum 2048-bit, prefer 4096-bit
     - ED25519: 256-bit (modern, recommended)
   - Suggest upgrading old/weak keys

6. **Delete old/unused keys**
   - For each key user wants to remove:
     ```bash
     rm ~/.ssh/old_key
     rm ~/.ssh/old_key.pub
     ```
   - Update `~/.ssh/config` if key was referenced
   - Remove from ssh-agent: `ssh-add -d ~/.ssh/old_key`

7. **Generate new keys if needed**
   - Suggest ED25519 for new keys:
     ```bash
     ssh-keygen -t ed25519 -C "user@email.com"
     ```
   - Or RSA 4096:
     ```bash
     ssh-keygen -t rsa -b 4096 -C "user@email.com"
     ```

8. **Update permissions**
   - Ensure correct permissions:
     ```bash
     chmod 700 ~/.ssh
     chmod 600 ~/.ssh/id_*
     chmod 644 ~/.ssh/id_*.pub
     chmod 600 ~/.ssh/config
     ```

9. **Add keys to ssh-agent**
   - Add keys: `ssh-add ~/.ssh/id_ed25519`
   - Persist across reboots (add to `~/.bashrc`):
     ```bash
     eval "$(ssh-agent -s)"
     ssh-add ~/.ssh/id_ed25519
     ```

## Output

Provide a summary showing:
- List of SSH keys with details (type, length, fingerprint)
- Keys currently loaded in ssh-agent
- Keys deleted (if any)
- New keys generated (if any)
- Security recommendations
- Next steps for adding keys to services
