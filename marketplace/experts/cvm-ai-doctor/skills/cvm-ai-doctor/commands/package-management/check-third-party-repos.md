---
description: Identify packages from third-party repos that may be available in official repos
tags: [system, packages, repositories, optimization, project, gitignored]
---

You are helping the user identify packages installed from third-party repositories that might now be available in official Ubuntu repos.

## Process

1. **List all configured repositories**
   - Check `/etc/apt/sources.list`
   - Check `/etc/apt/sources.list.d/*`
   - Identify which are third-party (PPAs, custom repos)

2. **Identify packages from third-party sources**
   - Run: `apt list --installed | grep -v "ubuntu\|debian"`
   - For each PPA, find packages: `apt-cache policy <package>` shows source

3. **Check official repo availability**
   - For each third-party package:
     - Check if available in Ubuntu repos: `apt-cache policy <package>`
     - Compare versions (official might be newer or older)
     - Note if it's in `universe`, `multiverse`, or `main`

4. **Common candidates for migration**
   - Development tools (git, docker, etc.)
   - Media codecs
   - Drivers (graphics, etc.)
   - Programming languages (Python, Node.js, etc.)

5. **Evaluate risks and benefits**
   - Official repos: More stable, better security updates
   - PPAs: Often newer versions, specific features
   - Suggest migration if:
     - Official version is adequate
     - PPA is unmaintained
     - Security concerns

6. **Create migration plan**
   - For packages to migrate:
     - Remove third-party package
     - Remove PPA if no longer needed
     - Install from official repo
     - Test functionality

## Output

Provide a report showing:
- List of third-party repositories in use
- Packages installed from each third-party source
- Which packages are available in official repos
- Version comparison
- Migration recommendations with commands
- Warnings about potential breaking changes
