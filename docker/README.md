# Octop Docker Deployment

---

This directory contains the Docker build and deployment assets for Octop.

### Files

| File | Description |
|------|-------------|
| `Dockerfile` | Multi-stage image definition (build context is the repo root) |
| `../.dockerignore` | Build context ignore rules (applies to both Podman and BuildKit) |
| `docker_build.sh` | Build image from source (BuildKit cache enabled by default) |
| `docker-compose.yml` | One-command local / self-hosted deployment |
| `docker-compose.postgres.yml` | PostgreSQL (+ pgvector) for dual-backend dev/tests |
| `postgres/init-vector.sql` | Instance-level `CREATE EXTENSION vector` (initdb.d; **not** Octop migrations) |
| `docker-entrypoint.sh` | Container entrypoint: first-run init + start server |

### Quick start

**Option 1: Compose (recommended)**

From the repository root:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Open `http://localhost:8088`. First-boot credentials are written to `~/octop-login.txt` (`/data/octop-login.txt` in the container; override with `OCTOP_DEFAULT_PASSWORD`). Password must be ≥8 characters with letters and digits.

**Option 2: Build script**

```bash
bash docker/docker_build.sh
docker run -d \
  --name octop \
  -p 8088:8088 \
  -v octop-data:/data/.octop \
  -e HOME=/data \
  octop:latest
```

### Faster downloads (China mirrors)

Pass mirror env vars when building:

```bash
PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple \
PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
APT_MIRROR=mirrors.cloud.tencent.com \
bash docker/docker_build.sh
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOME` | `/data` | Must be `/data` so `~/.octop` maps to the data volume |
| `OCTOP_PORT` | `8088` | HTTP listen port |
| `OCTOP_DEFAULT_PASSWORD` | — | Optional first-run admin password (≥8 chars, letters + digits) |
| `OCTOP_ADMIN_USERNAME` | `admin` | Initial admin username |
| `OCTOP_DATABASE_URL` | — | PostgreSQL DSN (or other `OCTOP_DATABASE_*`; see [configuration.md](../docs/configuration.md)) |
| `OCTOP_DATABASE_DRIVER` | — | `sqlite` \| `postgresql` when overriding defaults via env |
| `OPENAI_API_KEY` | — | OpenAI-compatible API key |
| `DASHSCOPE_API_KEY` | — | Alibaba DashScope API key |

For Compose, put these in `docker/.env`. Values only reach the container if listed under `environment:` in `docker-compose.yml` (Compose interpolates `.env`; it does not auto-export every key). Alternatively write the same keys into the mounted data dir as `~/.octop/env`.

### Data persistence

- Compose mounts host `~/.octop` → container `/data/.octop`
- `docker run` example uses named volume `octop-data`
- First boot runs `octop init`; credentials are written to `~/octop-login.txt` (`/data/octop-login.txt` in the container; override with `OCTOP_DEFAULT_PASSWORD`).

### Health check

The image probes `GET /api/health`:

```bash
curl http://localhost:8088/api/health
```

### Operations

```bash
docker logs -f octop
docker exec -it octop octop --version
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d --build
```
