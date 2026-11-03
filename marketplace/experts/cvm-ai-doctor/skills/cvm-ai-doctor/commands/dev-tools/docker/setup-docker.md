# Check and Setup Docker

You are helping the user check if Docker is configured and set it up if needed.

## Your tasks:

1. **Check if Docker is already installed:**
   - Check Docker: `docker --version`
   - Check Docker Compose: `docker-compose --version` or `docker compose version`
   - Check Docker service: `systemctl status docker`

2. **If Docker is installed, verify configuration:**
   - Check Docker info: `docker info`
   - Check user can run Docker: `docker ps`
   - If permission denied, user needs to be added to docker group
   - Check Docker storage driver and location
   - Check Docker network configuration

3. **If Docker is NOT installed, proceed with installation:**

   **Remove old versions:**
   ```bash
   sudo apt-get remove docker docker-engine docker.io containerd runc
   ```

   **Update and install prerequisites:**
   ```bash
   sudo apt-get update
   sudo apt-get install ca-certificates curl gnupg lsb-release
   ```

   **Add Docker's official GPG key:**
   ```bash
   sudo mkdir -p /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   ```

   **Set up repository:**
   ```bash
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   ```

   **Install Docker Engine:**
   ```bash
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

4. **Post-installation setup:**

   **Enable Docker service:**
   ```bash
   sudo systemctl enable docker
   sudo systemctl start docker
   ```

   **Add user to docker group:**
   ```bash
   sudo usermod -aG docker $USER
   ```
   Then log out and back in, or run: `newgrp docker`

5. **Verify Docker installation:**
   ```bash
   docker --version
   docker run hello-world
   docker ps
   docker images
   ```

6. **Install Docker Compose (if not included):**
   Modern Docker includes Compose v2 as a plugin.
   Check: `docker compose version`

   If needed, install standalone:
   ```bash
   sudo apt-get install docker-compose-plugin
   ```

7. **Configure Docker daemon (optional):**
   Edit `/etc/docker/daemon.json`:

   ```json
   {
     "log-driver": "json-file",
     "log-opts": {
       "max-size": "10m",
       "max-file": "3"
     },
     "storage-driver": "overlay2",
     "dns": ["8.8.8.8", "8.8.4.4"]
   }
   ```

   Then restart: `sudo systemctl restart docker`

8. **Check Docker storage location:**
   ```bash
   docker info | grep "Docker Root Dir"
   sudo du -sh /var/lib/docker
   ```

   If storage is on a small partition, consider changing location.

9. **Configure storage location (if needed):**
   In `/etc/docker/daemon.json`:
   ```json
   {
     "data-root": "/new/path/to/docker"
   }
   ```

   Then:
   ```bash
   sudo systemctl stop docker
   sudo mv /var/lib/docker /new/path/to/docker
   sudo systemctl start docker
   ```

10. **Set up Docker networking:**
    Check networks:
    ```bash
    docker network ls
    ```

    Create custom networks if needed:
    ```bash
    docker network create my-network
    ```

11. **Configure resource limits (optional):**
    For laptops/desktops, may want to limit resources:
    In `/etc/docker/daemon.json`:
    ```json
    {
      "default-ulimits": {
        "nofile": {
          "Name": "nofile",
          "Hard": 64000,
          "Soft": 64000
        }
      }
    }
    ```

12. **Set up Docker Hub authentication (optional):**
    ```bash
    docker login
    ```

13. **Test Docker functionality:**
    Run various test commands:
    ```bash
    docker run hello-world
    docker run -it ubuntu bash
    docker ps -a
    docker images
    docker system info
    ```

14. **Install useful Docker tools (optional):**
    Ask user if they want:
    - **Portainer** (Docker management UI)
    - **ctop** (Container monitoring)
    - **lazydocker** (Terminal UI for Docker)

    ```bash
    # ctop
    sudo wget -O /usr/local/bin/ctop https://github.com/bcicen/ctop/releases/download/v0.7.7/ctop-0.7.7-linux-amd64
    sudo chmod +x /usr/local/bin/ctop
    ```

15. **Configure Docker logging:**
    Check current logging:
    ```bash
    docker info | grep "Logging Driver"
    ```

    Configure in `/etc/docker/daemon.json`:
    ```json
    {
      "log-driver": "json-file",
      "log-opts": {
        "max-size": "10m",
        "max-file": "5",
        "labels": "production"
      }
    }
    ```

16. **Set up Docker cleanup:**
    Suggest adding to crontab:
    ```bash
    # Clean up unused containers, images, networks weekly
    0 3 * * 0 docker system prune -af --volumes
    ```

    Or show manual cleanup:
    ```bash
    docker system prune -a
    docker volume prune
    docker network prune
    ```

17. **Check for common issues:**
    - Docker daemon not running: `sudo systemctl start docker`
    - Permission denied: `sudo usermod -aG docker $USER` and re-login
    - Storage full: `docker system df` and cleanup
    - Network issues: Check DNS in daemon.json
    - Firewall blocking: Check ufw/iptables

18. **Provide best practices:**
    - Don't run containers as root when possible
    - Use Docker Compose for multi-container apps
    - Tag images properly
    - Clean up regularly with `docker system prune`
    - Use .dockerignore files
    - Monitor disk usage: `docker system df`
    - Use specific image tags, not `latest`
    - Scan images for vulnerabilities: `docker scan <image>`
    - Keep Docker updated
    - Use multi-stage builds to reduce image size
    - Limit container resources in production

19. **Show basic Docker commands:**
    - `docker run <image>` - Run a container
    - `docker ps` - List running containers
    - `docker ps -a` - List all containers
    - `docker images` - List images
    - `docker pull <image>` - Pull an image
    - `docker build -t <name> .` - Build an image
    - `docker exec -it <container> bash` - Enter container
    - `docker logs <container>` - View logs
    - `docker stop <container>` - Stop container
    - `docker rm <container>` - Remove container
    - `docker rmi <image>` - Remove image
    - `docker compose up` - Start compose stack
    - `docker system prune` - Clean up

20. **Report findings:**
    Summarize:
    - Docker installation status
    - Version information
    - User permissions status
    - Storage configuration
    - Service status
    - Any issues found

## Important notes:
- User must log out and back in after being added to docker group
- Docker can use significant disk space - monitor it
- Don't run untrusted images
- Docker Desktop is different from Docker Engine (we're installing Engine)
- Rootless Docker is available for better security but more complex
- Docker Compose v2 is now a plugin (`docker compose` not `docker-compose`)
- Keep Docker updated for security patches
