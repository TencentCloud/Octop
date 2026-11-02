# Install SDKMAN on Linux

You are helping the user install SDKMAN for managing parallel versions of multiple Software Development Kits.

## Your tasks:

1. **Check if SDKMAN is already installed:**
   - Check: `sdk version` or `which sdk`
   - Check for SDKMAN directory: `ls -la ~/.sdkman`
   - If already installed, ask if they want to update it

2. **Check prerequisites:**
   SDKMAN requires:
   - curl: `curl --version`
   - zip/unzip: `which zip unzip`
   - bash or zsh shell

   Install missing prerequisites:
   ```bash
   sudo apt update
   sudo apt install curl zip unzip
   ```

3. **Download and install SDKMAN:**
   ```bash
   curl -s "https://get.sdkman.io" | bash
   ```

   The installer will:
   - Install to `~/.sdkman`
   - Add initialization to ~/.bashrc or ~/.zshrc
   - Set up sdk command

4. **Initialize SDKMAN in current shell:**
   ```bash
   source "$HOME/.sdkman/bin/sdkman-init.sh"
   ```

5. **Verify installation:**
   ```bash
   sdk version
   sdk help
   ```

6. **Show available SDKs:**
   ```bash
   sdk list
   ```

   Common SDKs available:
   - Java (various distributions: OpenJDK, Graal, Corretto, etc.)
   - Gradle
   - Maven
   - Kotlin
   - Scala
   - Groovy
   - Spring Boot
   - Micronaut
   - And many more

7. **Install a few common SDKs (ask user first):**

   **Java:**
   ```bash
   sdk list java
   sdk install java  # installs latest stable
   # Or specific version:
   # sdk install java 17.0.9-tem
   ```

   **Gradle:**
   ```bash
   sdk install gradle
   ```

   **Maven:**
   ```bash
   sdk install maven
   ```

8. **Show basic SDKMAN usage:**
   Explain to the user:
   - `sdk list <sdk>` - List available versions of an SDK
   - `sdk install <sdk> <version>` - Install specific version
   - `sdk install <sdk>` - Install latest stable
   - `sdk uninstall <sdk> <version>` - Remove a version
   - `sdk use <sdk> <version>` - Use version for current shell
   - `sdk default <sdk> <version>` - Set default version
   - `sdk current <sdk>` - Show current version in use
   - `sdk current` - Show all current versions
   - `sdk upgrade <sdk>` - Upgrade to latest version
   - `sdk update` - Update SDK list
   - `sdk selfupdate` - Update SDKMAN itself

9. **Configure SDKMAN (optional):**
   Edit `~/.sdkman/etc/config`:

   ```bash
   # Auto answer 'yes' to all prompts
   sdkman_auto_answer=true

   # Automatically use Java version from .sdkmanrc
   sdkman_auto_env=true

   # Check for SDK updates on login
   sdkman_checkup_enable=true

   # Automatically selfupdate
   sdkman_selfupdate_enable=true
   ```

10. **Set up project-specific SDK versions:**
    Create `.sdkmanrc` file in project root:
    ```bash
    java=17.0.9-tem
    gradle=8.4
    maven=3.9.5
    ```

    Enable auto-env: `sdk env` or `sdk env install`

11. **Verify PATH and environment:**
    ```bash
    which java
    java -version
    echo $JAVA_HOME
    ```

12. **Show how to switch Java versions:**
    Demonstrate:
    ```bash
    sdk list java
    sdk install java 11.0.21-tem
    sdk install java 17.0.9-tem
    sdk use java 11.0.21-tem
    java -version
    sdk default java 17.0.9-tem
    ```

13. **Offline mode (optional):**
    Explain offline mode for when internet is unavailable:
    ```bash
    sdk offline enable
    sdk offline disable
    ```

14. **Flush and clean:**
    ```bash
    sdk flush  # Clear caches
    sdk flush temp  # Clear temporary files
    ```

15. **Provide best practices:**
    - Run `sdk update` regularly to refresh SDK lists
    - Run `sdk selfupdate` to keep SDKMAN current
    - Use `sdk current` to verify active versions
    - Use `.sdkmanrc` files for project-specific versions
    - Enable `sdkman_auto_env` for automatic version switching
    - Use `sdk env` when entering project directories
    - Keep multiple Java versions for different projects
    - Set sensible defaults with `sdk default`
    - SDKMAN doesn't require sudo
    - Check `~/.sdkman/candidates/` to see installed SDKs

16. **Troubleshooting:**
    - If `sdk` command not found, source the init script
    - Check `~/.bashrc` has SDKMAN initialization
    - Restart shell or source bashrc: `source ~/.bashrc`
    - Check PATH: `echo $PATH | grep sdkman`
    - Verify SDKMAN directory exists: `ls ~/.sdkman`

## Important notes:
- SDKMAN is user-level, doesn't require sudo
- Each SDK version is kept separate in `~/.sdkman/candidates/`
- Can coexist with system Java or other installation methods
- Using `sdk use` only affects current shell
- Using `sdk default` affects all new shells
- .sdkmanrc files are project-specific
- SDKMAN is particularly popular in JVM ecosystem
- Bash completion is included
