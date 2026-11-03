---
description: Review installed MCP servers and work with user to add new ones
tags: [mcp, ai, configuration, servers, project, gitignored]
---

You are helping the user manage their MCP (Model Context Protocol) servers.

## Process

1. **Check MCP configuration**
   - Look for MCP config: `~/mcp/` or `~/.config/mcp/`
   - Check Claude Code config: `~/.config/claude/`
   - Identify MCP server config files

2. **List currently installed MCP servers**
   - Parse configuration files
   - For each server, show:
     - Server name
     - Server type/purpose
     - Status (running/stopped)
     - Configuration details

3. **Check running MCP servers**
   - Look for running processes:
     ```bash
     ps aux | grep mcp
     ```
   - Check if servers are accessible

4. **Suggest useful MCP servers**

   **Common MCP servers:**
   - Filesystem MCP (file operations)
   - GitHub MCP (GitHub integration)
   - Database MCP (PostgreSQL, SQLite, etc.)
   - Browser MCP (web automation)
   - Context7 MCP (documentation)
   - Memory MCP (persistent memory)
   - Search MCP (web search)

5. **Install new MCP servers**
   - For each server user wants:
     - Check installation method (npm, pip, docker, etc.)
     - Install dependencies
     - Configure server
     - Add to MCP config

   **Example: Installing filesystem MCP**
   ```bash
   npm install -g @anthropic/mcp-server-filesystem
   ```

   **Example: Installing custom MCP server**
   ```bash
   git clone <repo-url>
   cd <repo>
   npm install
   ```

6. **Configure MCP servers**
   - Add server to config file
   - Example config:
     ```json
     {
       "mcpServers": {
         "filesystem": {
           "command": "mcp-server-filesystem",
           "args": ["/path/to/allowed/directory"]
         },
         "github": {
           "command": "mcp-server-github",
           "env": {
             "GITHUB_TOKEN": "your-token-here"
           }
         }
       }
     }
     ```

7. **Test MCP server connectivity**
   - Start servers
   - Verify they're accessible by Claude Code
   - Test basic operations

8. **Document MCP setup**
   - Offer to create `~/mcp/README.md` documenting:
     - Installed servers
     - Configuration
     - Usage examples
     - Troubleshooting

9. **Suggest workflows**
   - Recommend MCP server combinations for common tasks
   - Show example use cases

## Output

Provide a summary showing:
- Currently installed MCP servers
- Server status and configuration
- New servers installed (if any)
- Configuration changes made
- Usage examples
- Next steps or recommendations
