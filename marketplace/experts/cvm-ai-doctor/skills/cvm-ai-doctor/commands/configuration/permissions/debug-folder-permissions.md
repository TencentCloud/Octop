# Debug System Folder Permissions

You are helping the user debug systemwide folder permissions and ensure they are set appropriately.

## Your tasks:

1. **Gather information from user:**
   Ask:
   - Are they experiencing specific permission errors?
   - Which directories or operations are affected?
   - What user/group should have access?

2. **Check common system directories:**

   **Root filesystem:**
   ```bash
   ls -ld /
   # Should be: drwxr-xr-x root root
   ```

   **Essential system directories:**
   ```bash
   ls -ld /bin /sbin /usr /usr/bin /usr/sbin /lib /lib64
   # Should be: drwxr-xr-x root root
   ```

   **Variable data:**
   ```bash
   ls -ld /var /var/log /var/tmp
   # /var: drwxr-xr-x root root
   # /var/log: drwxrwxr-x root syslog (or root root)
   # /var/tmp: drwxrwxrwt root root (sticky bit)
   ```

   **Temporary directories:**
   ```bash
   ls -ld /tmp
   # Should be: drwxrwxrwt root root (sticky bit important!)
   ```

   **Home directories:**
   ```bash
   ls -ld /home /home/$USER
   # /home: drwxr-xr-x root root
   # /home/$USER: drwxr-xr-x $USER $USER (or drwx------ for privacy)
   ```

3. **Check for permission issues:**

   **World-writable directories without sticky bit (security risk):**
   ```bash
   sudo find / -type d -perm -0002 ! -perm -1000 2>/dev/null
   ```

   **Files with SUID bit (potential security issue if unexpected):**
   ```bash
   sudo find / -type f -perm -4000 2>/dev/null
   ```

   **Files with SGID bit:**
   ```bash
   sudo find / -type f -perm -2000 2>/dev/null
   ```

4. **Check /etc permissions:**
   ```bash
   ls -la /etc | head -20
   # /etc itself: drwxr-xr-x root root
   # Most files should be 644 (rw-r--r--)
   # Some may be 640 or 600 for security
   ```

   **Sensitive files:**
   ```bash
   ls -l /etc/shadow /etc/gshadow /etc/ssh/sshd_config
   # /etc/shadow: -rw-r----- root shadow
   # /etc/ssh/sshd_config: -rw-r--r-- root root
   ```

5. **Check user home directory structure:**
   ```bash
   ls -la ~/ | grep "^d"
   ```

   Common directories and recommended permissions:
   - `~/.ssh`: 700 (drwx------)
   - `~/.ssh/id_rsa`: 600 (-rw-------)
   - `~/.ssh/id_rsa.pub`: 644 (-rw-r--r--)
   - `~/.ssh/authorized_keys`: 600 (-rw-------)
   - `~/.gnupg`: 700 (drwx------)
   - `~/bin`: 755 (drwxr-xr-x)
   - `~/.local`: 755 (drwxr-xr-x)
   - `~/.config`: 755 (drwxr-xr-x)

6. **Check /opt and /usr/local:**
   ```bash
   ls -ld /opt /usr/local /usr/local/bin
   # Typically: drwxr-xr-x root root
   # But may be group-writable for admin group
   ```

7. **Check mount points:**
   ```bash
   mount | grep "^/" | awk '{print $3}' | while read mp; do
     ls -ld "$mp"
   done
   ```

8. **Check ownership of user files:**
   Find files in home directory not owned by user:
   ```bash
   find ~/ -not -user $USER 2>/dev/null
   ```

9. **Check group memberships:**
   ```bash
   groups
   id
   ```

   Common groups users might need:
   - `sudo` - for administrative access
   - `docker` - for Docker access
   - `video` - for video devices
   - `audio` - for audio devices
   - `plugdev` - for removable devices
   - `dialout` - for serial ports

10. **Fix common issues:**

    **Fix sticky bit on /tmp:**
    ```bash
    sudo chmod 1777 /tmp
    ```

    **Fix ~/.ssh permissions:**
    ```bash
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/id_rsa
    chmod 644 ~/.ssh/id_rsa.pub
    chmod 600 ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/config
    ```

    **Fix ownership of home directory:**
    ```bash
    sudo chown -R $USER:$USER ~/
    ```

    **Fix common directories:**
    ```bash
    chmod 755 ~/.local ~/.config ~/bin
    ```

11. **Check for ACL (Access Control Lists):**
    ```bash
    getfacl /path/to/directory
    ```

    If ACLs are in use (indicated by `+` in ls -l):
    ```bash
    ls -la | grep "+"
    ```

12. **Check SELinux context (if enabled):**
    ```bash
    getenforce
    ls -Z /path/to/directory
    ```

13. **Check for immutable flags:**
    ```bash
    lsattr /path/to/file
    ```

    If files have `i` flag, they can't be modified even by root:
    ```bash
    sudo chattr -i /path/to/file
    ```

14. **Specific directory recommendations:**

    **/var/www (web server):**
    ```bash
    sudo chown -R www-data:www-data /var/www
    sudo find /var/www -type d -exec chmod 755 {} \;
    sudo find /var/www -type f -exec chmod 644 {} \;
    ```

    **/srv (service data):**
    ```bash
    sudo chown -R root:root /srv
    sudo chmod 755 /srv
    ```

    **Shared directories:**
    ```bash
    sudo chown root:groupname /shared/directory
    sudo chmod 2775 /shared/directory  # SGID bit for group
    ```

15. **Check logs for permission denials:**
    ```bash
    sudo journalctl -p err | grep -i "permission denied"
    dmesg | grep -i "permission denied"
    sudo grep "permission denied" /var/log/syslog
    ```

16. **Report findings:**
    Summarize:
    - Incorrect permissions on system directories
    - Security issues (world-writable without sticky, unexpected SUID)
    - User home directory issues
    - Files/directories with wrong ownership
    - Missing group memberships
    - ACL or SELinux issues

17. **Provide recommendations:**
    - Fix commands for identified issues
    - Whether to add user to specific groups
    - Security improvements for sensitive directories
    - Standard permission schemes for common directories
    - Whether to use ACLs for complex permission needs

## Important notes:
- Always backup or test in safe environment first
- Changing system permissions incorrectly can break the system
- Use sudo carefully when fixing permissions
- Don't recursively chmod/chown system directories without understanding
- Some non-standard permissions may be intentional
- Check application documentation for required permissions
- SELinux/AppArmor may also affect access beyond traditional permissions
- Sticky bit on /tmp is critical for security
- SUID/SGID bits on unexpected files are security risks
