You are helping Daniel install and set up a program from GitHub.

## Your task

1. **Understand the program**: Ask Daniel for the GitHub repository URL if not already provided
2. **Determine the category**: Analyze the program's purpose and select the most appropriate category from Daniel's `~/programs` directory structure:
   - `ai-ml`: AI and machine learning applications
   - `communication`: Communication tools
   - `data-testing`: Data testing utilities
   - `design`: Design software
   - `development`: Development tools
   - `media-graphics`: Media and graphics applications
   - `monitoring-iot`: Monitoring and IoT tools
   - `storage-backup`: Storage and backup utilities
   - `system-utilities`: System utilities

3. **Clone the repository**: Clone the GitHub repository to the appropriate subdirectory in `~/programs/[category]/`

4. **Analyze setup requirements**:
   - Check for README, INSTALL, or setup documentation
   - Look for dependency requirements (package.json, requirements.txt, Cargo.toml, etc.)
   - Identify build steps (Makefile, build scripts, etc.)

5. **Install dependencies**: Install any required dependencies using the appropriate package manager:
   - Python: `pip install -r requirements.txt` or `pip install -e .`
   - Node.js: `npm install` or `yarn install`
   - Rust: `cargo build --release`
   - System packages: `sudo apt install [packages]`

6. **Build if necessary**: Run any build commands specified in the documentation

7. **Create symlinks or add to PATH**: If the program has executables:
   - Either create symlinks in `~/.local/bin/` (or `/usr/local/bin/` with sudo)
   - Or document how to add the program to PATH

8. **Test the installation**: Verify the program runs correctly

9. **Document the installation**: Create a brief summary including:
   - Where the program was installed
   - Any configuration steps taken
   - How to run/access the program
   - Any additional setup needed

## Important notes

- Use `gh repo clone` when possible for authenticated GitHub access
- Preserve the program's directory structure
- Don't modify the original repository files unless necessary for configuration
- If unsure about the category, ask Daniel for guidance
- Always test before declaring success
