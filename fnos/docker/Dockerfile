# syntax=docker/dockerfile:1
# =============================================================================
# Octop — FnOS 专用构建（基于仓库源码，安装全部附加组件）
#
# 与上游 docker/Dockerfile 一致，但显式安装 desktop extra：
#   - desktop  （mss / pynput / pillow，桌面控制附加组件）
# Playwright Chromium 不再预装，浏览器自动化可在控制台按需安装。
#
# 构建上下文必须为仓库根目录（fnpack / CI 中以仓库根为 context）：
#   docker build -f fnos/docker/Dockerfile -t ghcr.io/tencentcloud/octop:latest .
#
# 国内加速（可选 build-arg）：
#   PIP_INDEX_URL / PIP_TRUSTED_HOST / NPM_REGISTRY / APT_MIRROR
# =============================================================================

# ---------------------------------------------------------------------------
# 阶段 1 — 前端构建（React / TypeScript → src/octop/dashboard）
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend-builder

ARG NODE_MAX_OLD_SPACE_SIZE=2048
ARG NPM_REGISTRY=
WORKDIR /build/dashboard

COPY dashboard/package.json dashboard/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi \
    && npm ci --prefer-offline --no-audit

COPY dashboard/ ./

RUN mkdir -p ../src/octop/dashboard
RUN NODE_ENV=production NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}" npx vite build

# ---------------------------------------------------------------------------
# 阶段 2 — Python 运行时 + 预构建前端 + 全部附加组件
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL maintainer="TencentCloud OrcaKit"
LABEL org.opencontainers.image.title="Octop"
LABEL org.opencontainers.image.description="Smarter self-hosted AI assistant — multi-user, multi-agent (FnOS build with all addons)."
LABEL org.opencontainers.image.source="https://github.com/TencentCloud/Octop"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/data \
    OCTOP_BIND_HOST=0.0.0.0 \
    OCTOP_PORT=8088 \
    OCTOP_LOG_LEVEL=info \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

ARG APT_MIRROR=

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    if [ -n "$APT_MIRROR" ]; then \
        printf 'Types: deb\nURIs: https://%s/debian\nSuites: trixie trixie-updates\nComponents: main contrib non-free non-free-firmware\n\nTypes: deb\nURIs: https://%s/debian-security\nSuites: trixie-security\nComponents: main contrib non-free non-free-firmware\n' \
            "$APT_MIRROR" "$APT_MIRROR" > /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app

# 仅改源码时可复用此层缓存（用 uv pip 安装，避免 uv.lock 冻结冲突）
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY --from=frontend-builder /build/src/octop/dashboard/ ./src/octop/dashboard/

COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 安装项目 + desktop 附加组件（Playwright Chromium 不预装，控制台可按需下载）
# UV_INDEX_URL 首选阿里云镜像加速；UV_DEFAULT_INDEX 保留 PyPI 作为兜底，
# 避免新发布的包（如 orcakit-harness-agent 0.9.16）尚未同步到镜像时构建失败。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv \
    && UV_DEFAULT_INDEX=https://pypi.org/simple \
       UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
       UV_INSECURE_HOST=mirrors.aliyun.com \
       uv pip install --python /app/.venv ".[desktop]" \
    && apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/* /tmp/*

ENV PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

RUN mkdir -p /data/.octop

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:${OCTOP_PORT:-8088}/api/health || exit 1"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD []
