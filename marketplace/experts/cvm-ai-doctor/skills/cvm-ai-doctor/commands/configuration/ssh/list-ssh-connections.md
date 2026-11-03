---
description: Review which SSH connection names/hosts the user has configured
tags: [ssh, configuration, hosts, network, project, gitignored]
---

You are helping the user review their SSH connection configurations.

## Process

1. **Check if SSH config exists**
   - Look for: `~/.ssh/config`
   - If not found, offer to create one

2. **Parse SSH config file**
   - Read `~/.ssh/config`
   - Extract Host entries
   - For each host, show:
     - Host alias
     - HostName (IP/domain)
     - User
     - Port
     - IdentityFile (SSH key)
     - Other options

3. **Display in organized format**
   - Present as table or list:
     ```
     Alias: server1
     HostName: 192.168.1.100
     User: admin
     Port: 22
     Key: ~/.ssh/id_rsa
     ---
     ```

4. **Check system-wide SSH config**
   - Also check `/etc/ssh/ssh_config` for global settings
   - Note any system-wide host configurations

5. **Test connectivity (optional)**
   - Ask if user wants to test connections
   - For each host:
     ```bash
     ssh -T user@host
     # or
     ssh -o ConnectTimeout=5 user@host "echo Connection successful"
     ```

6. **Identify stale connections**
   - Look for connections to:
     - IPs that might have changed
     - Servers that may no longer exist
     - Old project servers

7. **Suggest config improvements**
   - Recommend useful SSH config options:
     ```
     Host *
       ServerAliveInterval 60
       ServerAliveCountMax 3
       TCPKeepAlive yes
       ControlMaster auto
       ControlPath ~/.ssh/sockets/%r@%h-%p
       ControlPersist 600
     ```

8. **Offer to create new entries**
   - If user wants to add new SSH hosts
   - Template:
     ```
     Host shortname
       HostName hostname.com
       User username
       Port 22
       IdentityFile ~/.ssh/id_ed25519
       ForwardAgent yes
     ```

9. **Security check**
   - Verify file permissions: `chmod 600 ~/.ssh/config`
   - Look for insecure settings (password auth, etc.)

## Output

Provide a summary showing:
- List of configured SSH hosts
- Connection details for each
- Stale/inactive connections (if identified)
- Connectivity test results (if performed)
- Suggested improvements
- New entries added (if any)
