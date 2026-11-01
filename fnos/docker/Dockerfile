# syntax=docker/dockerfile:1
# =============================================================================
# Octop — 可选的源码镜像（飞牛 FPK 不使用本文件）
#
# 飞牛 Docker 版安装包复用 docker-publish 推送的
# ghcr.io/tencentcloud/octop:{version}，那份镜像由 docker/Dockerfile 构建。
# 本文件只在显式执行下面的命令时使用，构建上下文为仓库根目录：
#   docker build -f fnos/docker/Dockerfile -t octop:fnos-source .
#
# 与上游相比保留 desktop，并同样打进本地知识库运行时：
#   - desktop          （mss / pynput / pillow，桌面控制附加组件）
#   - local-embedding  （fastembed，本地 ONNX 知识库）
#   - knowledge-ocr    （rapidocr / onnxruntime / pymupdf）
# 这些依赖必须在镜像层。装进容器可写层的包会在重建后丢失，
# 数据卷里的设置和索引却还在。
# 另外用 bake-desktop.sh 装入虚拟桌面和系统 Chromium，但不启动。
# 桌面组件已包含浏览器，不再另下 Playwright Chromium。
# 运行时带 Node.js 20（node / npm / npx），供依赖 Node 的技能使用。
# 飞牛 Docker 版安装包不构建本文件，而是拉取由 docker/Dockerfile 打出的镜像；
# 两份 Dockerfile 的 Node 运行时保持一致。
# Laya 不打进镜像：CPU 版 PyTorch 加多语言检查点大约要 4 GB 磁盘。
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

LABEL maintainer="TencentCloud"
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
        libgl1 \
        libglib2.0-0 \
        curl \
        git \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

# 技能和专家 shell 会调用 node / npm / npx。从前端构建阶段复用 Node 20。
# Docker 拷贝会展开软链接，因此 npm / npx 在这里按原路径重建。
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version && npx --version

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app

# 仅改源码时可复用此层缓存（用 uv pip 安装，避免 uv.lock 冻结冲突）
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY --from=frontend-builder /build/src/octop/dashboard/ ./src/octop/dashboard/

COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/bake-desktop.sh /usr/local/bin/bake-desktop.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh /usr/local/bin/bake-desktop.sh

# 安装项目与附加组件。虚拟桌面和系统 Chromium 由后面的 bake-desktop.sh 装入，
# 不会启动。local-embedding / knowledge-ocr 与 desktop 一起装进镜像层，避免运行时
# 装进 overlay 后在容器重建时丢失。
# UV_INDEX_URL 首选阿里云镜像加速；UV_DEFAULT_INDEX 保留 PyPI 作为兜底，
# 避免新发布的包（如 octop-harness 0.9.16）尚未同步到镜像时构建失败。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv \
    && UV_DEFAULT_INDEX=https://pypi.org/simple \
       UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
       UV_INSECURE_HOST=mirrors.aliyun.com \
       uv pip install --python /app/.venv ".[desktop,local-embedding,knowledge-ocr]" \
    && /app/.venv/bin/python -c "import cv2, fastembed, huggingface_hub, mss, pynput, rapidocr, onnxruntime, pymupdf" \
    && apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/* /tmp/*

# Packages only. Xvnc stays stopped until the user enables the desktop.
RUN bash /usr/local/bin/bake-desktop.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

RUN mkdir -p /data/.octop

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:${OCTOP_PORT:-8088}/api/health || exit 1"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD []
