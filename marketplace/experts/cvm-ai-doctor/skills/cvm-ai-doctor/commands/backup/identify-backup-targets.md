---
description: Identify filesystem parts to backup and suggest inclusion patterns
tags: [backup, filesystem, strategy, rclone, project, gitignored]
---

You are helping the user identify which parts of their filesystem should be backed up and create appropriate inclusion patterns.

## Process

1. **Analyze filesystem structure**
   - Home directory size: `du -sh ~/*` or `du -h --max-depth=1 ~ | sort -h`
   - System directories to consider
   - External drives/mounts

2. **Categorize data by importance**

   **Critical (must backup):**
   - Documents: `~/Documents`
   - Development work: `~/repos`
   - Configuration files: `~/.config`, `~/.ssh`, `~/.gnupg`
   - Scripts: `~/scripts`, `~/.local/bin`
   - AI documentation: `~/ai-docs`

   **Important (should backup):**
   - Pictures/Photos
   - Videos (personal)
   - Music (if not streaming)
   - Downloads (selective)
   - Email (if local)

   **Optional (consider backing up):**
   - Application data: `~/.local/share`
   - Browser data (bookmarks, passwords)
   - Game saves

   **Exclude (don't backup):**
   - Caches: `~/.cache`
   - Temporary files: `/tmp`, `~/.tmp`
   - Virtual machines/disk images
   - Node modules: `node_modules/`
   - Python venvs: `venv/`, `.venv/`
   - Build artifacts: `target/`, `build/`, `dist/`
   - Large media files (if cloud-synced elsewhere)

3. **Identify special considerations**
   - Check for large directories: `du -h --max-depth=2 ~ | sort -h | tail -20`
   - Look for media libraries
   - Identify development projects with dependencies
   - Find version-controlled repos (can skip .git if remote exists)

4. **Create inclusion/exclusion patterns**

   **For rclone:**
   ```
   # Include patterns
   + /Documents/**
   + /repos/**
   + /.config/**
   + /.ssh/**
   + /.gnupg/**
   + /scripts/**
   + /.local/bin/**
   + /ai-docs/**
   + /Pictures/**

   # Exclude patterns
   - /.cache/**
   - /.local/share/Trash/**
   - /**/node_modules/**
   - /**/.venv/**
   - /**/venv/**
   - /**/__pycache__/**
   - /**/.git/**
   - /.thumbnails/**
   ```

   **For rsync:**
   ```bash
   --include='/Documents/***'
   --include='/repos/***'
   --exclude='**/.cache/'
   --exclude='**/node_modules/'
   --exclude='**/.venv/'
   ```

5. **Calculate backup size**
   - Estimate total backup size based on included directories
   - Consider compression potential
   - Plan for growth

6. **Suggest backup frequency**
   - Critical data: Daily or real-time sync
   - Important data: Weekly
   - Optional data: Monthly
   - System configs: After changes

7. **Create backup configuration file**
   - Offer to create `~/scripts/backup-config.txt` with patterns
   - Create `~/scripts/backup-estimate.sh` to calculate size

## Output

Provide a report showing:
- Categorized list of directories to backup
- Size estimates for each category
- Recommended inclusion/exclusion patterns (rclone and rsync format)
- Total estimated backup size
- Suggested backup frequency for each category
- Configuration file content
